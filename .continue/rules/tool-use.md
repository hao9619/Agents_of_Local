---
name: 正确调用文件工具
alwaysApply: true
---

- 只调用当前请求实际提供的工具，严格使用其名称和参数，不臆造工具名。
- 用户要求创建文件时，若可用，调用 create_new_file，参数为 filepath（含文件名的路径）和 contents（完整文件内容）。例如新建 HTML 要直接提供 HTML 内容，不生成代替创建操作的 Python 脚本。
- 文件已存在时，不再调用 create_new_file；先用 read_file 读取当前内容，再按实际提供的工具编辑。局部替换优先用 single_find_and_replace（filepath、old_string、new_string），old_string 必须与原文精确匹配。若提供 edit_existing_file，则使用 filepath、changes；只使用当前列表中存在的接口。
- 用户明确要求整体改写时，可使用实际可用的编辑工具替换全文；不能因此丢弃原任务要求。未授权删除时，不通过删除后新建绕过编辑工具。
- 不臆造 mkdir 或 write_file 工具。子目录创建按现有工具能力处理；必要时先创建根目录文件，不因缺少独立目录工具就声称不能写文件。
- 遇到 Tool not found，核对实际可用工具后纠正调用；遇到权限拒绝或真实写入错误，报告具体原因，不通过其他工具绕过限制。
- 只有工具返回成功才能声称文件已创建。若当前没有写入工具，明确说明缺失，再提供手动代码。
