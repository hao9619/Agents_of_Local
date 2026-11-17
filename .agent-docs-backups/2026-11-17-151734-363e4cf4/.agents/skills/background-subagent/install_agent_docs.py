#!/usr/bin/env python3
"""将同目录的四份 Agent 文档安装到指定项目；仅使用 Python 标准库。

用法（Python 3.9+）：
  python3 install_agent_docs.py                       # 输入项目路径后安装
  python3 install_agent_docs.py --project /项目路径
  python3 install_agent_docs.py --project /项目路径 --dry-run
  python3 install_agent_docs.py --project /项目路径 --overwrite
  python3 install_agent_docs.py --workspace /大项目路径 --project /大项目路径/子目录

请把本脚本和四份源 MD 放在同一目录。修改源 MD 后重新运行即可更新。
现有 AGENTS 内容保留；已被手改的安装文件默认拒绝覆盖。--overwrite 会先备份。
不修改全局配置，不安装软件，不启动后台任务，不执行 Git 命令。
根目录安装会携带本脚本，后续 Codex 可调用已安装的脚本按需配置子目录。
--workspace 将写入限制在指定根目录内：同一 Git 仓库引用公共文档，其他情况完整安装。
仅检查指定目录，不递归遍历或批量安装；自定义项目根配置需另行核对。

安装布局：
  项目/AGENTS.md（若非空 AGENTS.override.md 生效，则使用该文件）
  项目/.agents/skills/background-subagent/
      SKILL.md                         后台任务技能
      codex-subagent-model-selection.md 子代理规则
      documentation.md                 文档与目录规则
      git-multicomputer-workflow.md     Git 与多机接续规则
      install_agent_docs.py             子目录按需安装工具
      .installation.json               更新时的内容校验记录
  项目/.agent-docs-backups/时间-随机后缀/  更新已有文件时的备份

依据：
  https://learn.chatgpt.com/docs/build-skills
  https://learn.chatgpt.com/docs/agent-configuration/agents-md
项目技能通过 .agents/skills 发现；普通规则通过项目入口按需读取。
请在目标项目重新开启 Codex 会话，以加载更新后的 AGENTS 入口。
其他 Agent 是否自动识别这些入口，取决于其自身支持。
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid
from urllib.parse import quote


PACKAGE = "local-agent-guides"
SKILL_DIR = Path(".agents/skills/background-subagent")
MANIFEST = SKILL_DIR / ".installation.json"
BACKUPS = Path(".agent-docs-backups")
BEGIN = "<!-- BEGIN local-agent-guides -->"
END = "<!-- END local-agent-guides -->"
LEGACY_DOCUMENTS = ("codex-subagent-model-selection.md", "documentation.md")
DOCUMENTS = (*LEGACY_DOCUMENTS, "git-multicomputer-workflow.md")
ENTRY_NAMES = ("AGENTS.md", "AGENTS.override.md")


class InstallError(Exception):
    """可直接呈现给用户的安装错误。"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    """拒绝目标内的符号链接或 Windows junction，保持写入范围可预测。"""
    current = root
    for part in Path(relative).parts:
        if part in ("..", "/", "\\"):
            raise InstallError(f"无效的安装路径：{relative}")
        current = current / part
        if os.path.lexists(current):
            info = current.lstat()
            reparse = getattr(info, "st_file_attributes", 0) & getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
            )
            if current.is_symlink() or reparse:
                raise InstallError(f"目标路径含链接或 junction，请使用独立目录：{current}")
            if current != root / relative and not current.is_dir():
                raise InstallError(f"路径中的父级不是目录：{current}")
    return current


def read_optional(path):
    if not path.exists():
        return None
    if not path.is_file():
        raise InstallError(f"预期为普通文件：{path}")
    return path.read_bytes()


def load_sources(source):
    contents = {}
    for filename in (*DOCUMENTS, "background-subagent.md"):
        path = source / filename
        if filename == "background-subagent.md" and not path.exists():
            path = source / "SKILL.md"
        if not path.is_file():
            raise InstallError(f"缺少源文件：{path}。请把安装脚本和四份 MD 放在一起；旧安装请先用新版安装包更新。")
        data = path.read_bytes()
        text = data.decode("utf-8-sig")
        if not text.strip():
            raise InstallError(f"源文件为空：{path}")
        contents[filename] = data

    skill = contents.pop("background-subagent.md").decode("utf-8-sig").replace("\r\n", "\n")
    frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|$)", skill, re.S)
    if not frontmatter or not re.search(
        r"^name: background-subagent\s*$", frontmatter.group(1), re.M
    ) or not re.search(r"^description: \S.+$", frontmatter.group(1), re.M):
        raise InstallError("后台技能稿的 name/description 元数据不符合预期。")
    # 正式入口不再保留源文件中解释“技能说明稿如何安装”的编辑说明。
    skill = "\n\n".join(
        paragraph for paragraph in skill.split("\n\n")
        if not paragraph.startswith("本文以 `background-subagent.md` 保存")
    )
    for target in re.findall(r"\]\(([^)]+)\)", skill):
        if "://" not in target and not target.startswith("#"):
            if target.split("#", 1)[0] not in DOCUMENTS:
                raise InstallError(f"技能稿含未打包的本地引用：{target}")
    contents["SKILL.md"] = skill.encode("utf-8")
    script = source / "install_agent_docs.py"
    if not script.is_file():
        raise InstallError(f"缺少安装工具：{script}")
    contents[script.name] = script.read_bytes()
    return {SKILL_DIR / name: data for name, data in contents.items()}


def make_block(base=None):
    base = quote(base or SKILL_DIR.as_posix(), safe="/.")
    return (
        f"{BEGIN}\n"
        "## 本项目通用协作规则\n\n"
        "以下路径相对于本入口文件所在目录。用户明确要求及本项目具体约定"
        "优先于引用文档中的默认建议。\n\n"
        f"- 开始或恢复工作时，读取 [文档与目录规范]({base}/documentation.md) 中的多层项目安装与会话交接规则，"
        "再读本目录现有状态入口，核对用户指定的会话角色、职责、活动任务及文件负责人。"
        "未被用户指定时不得自称主会话；缺少交接信息时不编造。文档和目录维护也遵循该规范。\n"
        f"- 在通过 GitHub 多机接续的项目首次接入或规则变化时，读取 [Git 与多机接续规范]({base}/git-multicomputer-workflow.md)，后续复用并按需查阅。"
        "将代码、必要证据和当前进展在工作过程中写入根仓库可收录的位置，结束前核查本轮增量；"
        "不等用户要求再整理，不把干净状态当作已经同步。沿用一个主分支，Git 暂存、提交和推送默认由用户执行。\n"
        f"- 创建任何辅助会话前，读取 [子代理模型与交接规则]({base}/codex-subagent-model-selection.md)，"
        "向用户说明任务和监管建议，等待用户选择自己监管或 Codex 监管；已明确的同一任务选择无需重复询问。\n"
        f"- 根目录已授权按需配置子目录时，在实际进入子目录工作或准备交接前检查其入口。"
        f"使用 [安装工具]({base}/install_agent_docs.py) 的 --workspace 根目录 --project 目标子目录，先 --dry-run 再执行。"
        "只处理本轮可写范围，保留已有约定；不递归安装、不自动使用 --overwrite、不创建会话。"
        "规则入口未准备好的独立目录，应由已有规则的会话先配置，再由用户开启主会话。\n"
        f"- 用户明确要求后台执行，或查询、停止、恢复已有后台任务时，"
        f"使用 [background-subagent 技能]({base}/SKILL.md)，并核对当前环境的执行能力与权限。"
        "普通任务耗时较长不自动触发后台执行。\n"
        f"{END}"
    ).encode("utf-8")


def block_span(data):
    start, end = BEGIN.encode(), END.encode()
    if data.count(start) != data.count(end) or data.count(start) > 1:
        raise InstallError("入口中的安装器标记缺失或重复，请先修复标记，原文件未改动。")
    if start not in data:
        return None
    left, end_start = data.index(start), data.index(end)
    if end_start < left:
        raise InstallError("入口中的安装器标记顺序错误，原文件未改动。")
    return left, end_start + len(end)


def load_manifest(data):
    if data is None:
        return None
    try:
        record = json.loads(data)
        old_files = {str(SKILL_DIR / name) for name in (*LEGACY_DOCUMENTS, "SKILL.md")}
        old_with_script = old_files | {str(SKILL_DIR / "install_agent_docs.py")}
        full_files = old_with_script | {str(SKILL_DIR / "git-multicomputer-workflow.md")}
        inventory = set(record["files"])
        valid = (
            record["package"] == PACKAGE and record["schema"] in (1, 2)
            and record["entry_file"] in ENTRY_NAMES
            and (inventory in (old_files, old_with_script, full_files)
                 or (not inventory and record.get("mode") == "reference" and record["schema"] == 2))
            and all(re.fullmatch(r"[0-9a-f]{64}", value)
                    for value in [record["block_sha256"], *record["files"].values()])
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise InstallError("已有 .installation.json 无效或属于其他安装器；请先检查，未修改项目。")
    return record


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".agent-docs-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(project, source, dry_run=False, overwrite=False, reference=None):
    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise InstallError(f"项目目录不存在：{root}。请先创建项目目录或检查路径。")
    desired = load_sources(Path(source))
    base = None
    if reference is not None:
        base = Path(os.path.relpath(Path(reference).resolve() / SKILL_DIR, root)).as_posix()
        desired = {}
    previous = {}
    for relative in (*desired, MANIFEST, *map(Path, ENTRY_NAMES)):
        previous[relative] = read_optional(safe_path(root, relative))
    manifest = load_manifest(previous[MANIFEST])
    override = previous[Path("AGENTS.override.md")]
    entry = Path("AGENTS.override.md" if override and override.decode("utf-8-sig").strip() else "AGENTS.md")
    conflicts = []

    for relative, data in desired.items():
        old = previous[relative]
        if old is not None and old != data:
            baseline = manifest["files"].get(relative.as_posix()) if manifest else None
            if digest(old) != baseline:
                conflicts.append(relative.as_posix())

    # 若用户后来启用了 override，将旧入口中的受管块迁到实际生效的入口。
    entry_paths = [entry]
    if manifest and Path(manifest["entry_file"]) != entry:
        entry_paths.insert(0, Path(manifest["entry_file"]))
    if reference is not None and manifest and manifest["files"]:
        raise InstallError("目标已有完整安装，请继续更新本地副本，不自动改为引用模式。")
    block = make_block(base)
    for relative in entry_paths:
        old = previous[relative] or b""
        old.decode("utf-8-sig")  # 保持非受管部分的原始字节；拒绝无法识别的编码。
        span = block_span(old)
        if span:
            existing = old[span[0]:span[1]]
            baseline = manifest["block_sha256"] if manifest and manifest["entry_file"] == str(relative) else None
            if existing != block and digest(existing) != baseline:
                conflicts.append(f"{relative} 的安装器维护区")
            replacement = block if relative == entry else b""
            desired[relative] = old[:span[0]] + replacement + old[span[1]:]
        elif relative == entry:
            separator = b"" if not old or old.endswith(b"\n\n") else b"\n" if old.endswith(b"\n") else b"\n\n"
            desired[relative] = old + separator + block + b"\n"

    if conflicts and not overwrite:
        names = "\n  ".join(conflicts)
        raise InstallError(
            f"检测到已有内容或安装后手动修改，未写入任何文件：\n  {names}\n"
            "请先检查差异；确需用源文档替换时添加 --overwrite，覆盖前仍会备份。"
        )

    new_record = {
        "package": PACKAGE, "schema": 2, "entry_file": str(entry),
        "mode": "reference" if reference is not None else "full",
        "block_sha256": digest(block),
        "files": {relative.as_posix(): digest(data) for relative, data in desired.items()
                  if relative.parent == SKILL_DIR},
    }
    # 无实际变更时不更新时间、制造备份或触碰文件 mtime。
    if not any(previous.get(path) != data for path, data in desired.items()) and manifest:
        if all(manifest.get(key) == value for key, value in new_record.items()):
            print(f"已是最新版本，无需修改：{root}")
            return
    new_record["installed_at_utc"] = datetime.now(timezone.utc).isoformat()
    desired[MANIFEST] = (json.dumps(new_record, ensure_ascii=False, indent=2) + "\n").encode()
    changes = {relative: data for relative, data in desired.items() if previous.get(relative) != data}

    # 所有文件及备份路径在写入前检查。manifest 最后写入，失败时恢复已经写入的文件。
    safe_path(root, BACKUPS)
    if (root / BACKUPS).exists() and not (root / BACKUPS).is_dir():
        raise InstallError(f"备份路径不是目录：{root / BACKUPS}")
    print(f"{'预览' if dry_run else '安装'}到：{root}")
    for relative in changes:
        print(f"  {'新建' if previous.get(relative) is None else '更新'} {relative}")
    if dry_run:
        print("仅预览，未创建目录、备份或文件。")
        return

    modes = {p: stat.S_IMODE((root / p).stat().st_mode) if previous.get(p) is not None else 0o644
             for p in changes}
    backup = None
    if any(previous.get(path) is not None for path in changes):
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
        backup = root / BACKUPS / f"{stamp}-{uuid.uuid4().hex[:8]}"
        for relative in changes:
            if previous.get(relative) is not None:
                atomic_write(backup / relative, previous[relative], modes[relative])
        print(f"旧文件备份：{backup}")

    written = []
    try:
        for relative, data in changes.items():
            path = safe_path(root, relative)
            if read_optional(path) != previous.get(relative):
                raise InstallError(f"安装期间文件被其他程序修改，已停止：{path}")
            atomic_write(path, data, modes[relative])
            written.append(relative)
    except (OSError, InstallError) as error:
        rollback_errors = []
        for relative in reversed(written):
            try:
                path = safe_path(root, relative)
                if read_optional(path) != changes[relative]:
                    raise InstallError(f"{relative} 已被其他程序修改，未覆盖它")
                if previous.get(relative) is None:
                    path.unlink()
                else:
                    atomic_write(path, previous[relative], modes[relative])
            except (OSError, InstallError) as rollback_error:
                rollback_errors.append(str(rollback_error))
        details = "；".join(rollback_errors) if rollback_errors else "已恢复本轮写入的文件（可能保留空目录）"
        raise InstallError(f"安装未完成：{error}。{details}。备份：{backup or '本轮没有旧文件'}") from error

    print(f"安装完成。入口：{root / entry}")
    print(f"规则模式：{'引用 ' + str(reference) if reference is not None else '完整安装（含子目录安装工具）'}")
    if reference is None:
        print(f"后台技能：{root / SKILL_DIR / 'SKILL.md'}")
    print("请在目标项目重新开启 Codex 会话。可要求 Agent 列出本项目生效的规则与技能进行核对。")
    print("源文档修改后重新运行同一命令即可更新；本次没有修改全局配置或启动后台任务。")


def git_boundary(directory):
    """只检查祖先的 .git 标记，支持仓库目录及 worktree/submodule 的 .git 文件。"""
    for parent in (directory, *directory.parents):
        if os.path.lexists(parent / ".git"):
            return parent
    return None


def ensure_child(workspace, project, dry_run=False, overwrite=False):
    root = Path(workspace).expanduser().resolve()
    # 在 resolve 前检查链接，不能把指向工作区外的目录当作允许写入的子目录。
    target = Path(os.path.abspath(Path(project).expanduser()))
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise InstallError(f"目标必须位于指定大项目根目录内：{root}") from error
    safe_path(root, relative)
    if target == root or not target.is_dir():
        raise InstallError("按需安装的目标必须是根目录内已存在的子目录。")
    source = safe_path(root, SKILL_DIR)
    desired = load_sources(source)
    record = load_manifest(read_optional(safe_path(root, MANIFEST)))
    if not record or not record["files"]:
        raise InstallError("指定根目录尚未完整安装，请先在该根目录运行普通安装。")
    # 在指定边界内选最近的完整规则来源，避免从大根目录调用时在独立仓库内重复复制。
    provider = root
    for parent in target.parents:
        if parent == root:
            break
        candidate = read_optional(safe_path(parent, MANIFEST))
        if candidate is not None:
            parent_record = load_manifest(candidate)
            if parent_record["files"]:
                provider = parent
                source = safe_path(provider, SKILL_DIR)
                break
    # 已有本地技能时保留本地模式，由 install 的冲突保护决定能否更新。
    local_skill = safe_path(target, SKILL_DIR / "SKILL.md")
    boundary = git_boundary(provider)
    shared = boundary is not None and boundary == git_boundary(target) and not local_skill.exists()
    print("按需配置：同一 Git 仓库，引用公共规则。" if shared
          else "按需配置：独立仓库、无 Git 边界或已有本地技能，使用完整安装。")
    install(target, source, dry_run, overwrite, reference=provider if shared else None)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="将四份本地 Agent 文档安装到指定项目（Python 3.9+，无需额外依赖）。",
        epilog="不传 --project 时询问项目目录；输入路径中的 ~ 会展开。源 MD 须与脚本位于同一目录。",
    )
    parser.add_argument("--project", type=Path, help="已有项目的根目录；可包含中文和空格")
    parser.add_argument("--workspace", type=Path, help="已完整安装的大项目根目录；仅按需配置其指定子目录")
    parser.add_argument("--dry-run", action="store_true", help="只显示将修改的文件，不写入")
    parser.add_argument("--overwrite", action="store_true", help="备份后替换手动修改过的受管内容")
    args = parser.parse_args(argv)
    try:
        project = args.project
        if project is None:
            answer = input("请输入要安装到的项目根目录（空输入取消）：").strip()
            if len(answer) >= 2 and answer[0] == answer[-1] and answer[0] in "\"'":
                answer = answer[1:-1]
            if not answer:
                print("已取消，未修改文件。")
                return 0
            project = Path(answer)
        if args.workspace is not None:
            ensure_child(args.workspace, project, args.dry_run, args.overwrite)
        else:
            install(project, Path(__file__).resolve().parent, args.dry_run, args.overwrite)
        return 0
    except (InstallError, OSError, UnicodeError) as error:
        print(f"安装失败：{error}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。若写入阶段被强制中断，请核对目标文件和备份后重新运行。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
