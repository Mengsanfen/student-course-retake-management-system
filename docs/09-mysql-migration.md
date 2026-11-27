# 本地MySQL接入与数据同步记录

日期：2026-11-27；用户授权使用本机MySQL创建项目数据库并同步现有数据。

## 1. 当前连接

- 实例：127.0.0.1:3306，MySQL 8.0.36。
- 业务库：retake_management；独立测试库：retake_management_test。
- 字符集：utf8mb4；排序规则：utf8mb4_0900_as_cs，保留账号等字符串大小写语义。
- 存储引擎：InnoDB；事务隔离：READ COMMITTED。
- 应用账户：retake_app，仅本地127.0.0.1，权限范围为两个项目数据库；不修改其他库或全局配置。
- 连接信息保存在忽略的backend/.env和backend/.env.mysql-test。root密码仅在交互提示中使用，未写文件、命令参数或文档。

## 2. 同步过程

确认两个目标库不存在 → 创建项目库及受限账号 → 暂停原后端写入 → 用SQLite备份API生成包含WAL已提交数据的一致性备份 → 在MySQL执行Alembic 0001 → 按外键依赖顺序插入原主键及全部字段 → 同一事务内逐表比较所有列内容 → 提交 → 启动MySQL连接的后端。

未删除SQLite原库或证明材料。材料目录仍为backend/.uploads，因此只迁移材料元数据，文件引用与文件大小另行核对。同步保留申请、审核轨迹、通知已读状态、成绩、考试时间、密码哈希及会话；过期会话继续遵循正常清理规则。

| 表 | 同步行数 | 全列核对 |
| --- | --- | --- |
| departments | 2 | 一致 |
| users | 8 | 一致 |
| courses | 4 | 一致 |
| course_offerings | 4 | 一致 |
| enrollments | 6 | 一致 |
| attachments | 1 | 一致，文件存在且大小匹配 |
| deferral_applications | 1 | 一致 |
| approval_records | 3 | 一致 |
| notifications | 7 | 一致 |
| auth_sessions | 2 | 同步时一致，运行后按会话生命周期变化 |

Alembic版本记录由MySQL迁移生成，不从SQLite复制。同步是一次性导入，不启用两库双写；之后的操作写入MySQL。

## 3. 验证与可复现命令

实际HTTP验证：学生登录成功，课程4门，原申请状态APPROVED、审核记录3条，证明材料下载200且内容可读；退出成功。运行连接确认CURRENT_USER为retake_app@127.0.0.1，数据库为retake_management，所有表InnoDB。

双数据库回归：`powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -Database both`。两线程并发申请及审核在真实MySQL中验证。测试严格使用retake_management_test，不清理业务库。完整结果见06测试报告。

本地证据：.runtime/mysql-sync-report.json、.runtime/mysql-verification.json、.runtime/pytest-mysql.xml；不含密码或业务正文，不提交运行生成资料。

## 4. 备份与回退

原库：backend/.data/retake.sqlite3；迁移前独立备份：.runtime/backups/retake-before-mysql-*.sqlite3。证明材料保持原目录，不能删除。

如需要切回迁移时快照，应先停止后端、备份当前MySQL新增业务，再显式将DATABASE_URL改为保留的SQLite备份副本路径并验证；不会自动把MySQL新数据反向同步到旧SQLite。回退和正式恢复演练需保留数据并另行记录。
