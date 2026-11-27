# 高校学生课程缓考与重修管理系统

基于 B/S 架构的毕业设计。原始研究内容保留在项目根目录的 Word 文件中；需求细化、设计决策、代码和验证记录随功能一起维护。

## 当前阶段

M1已验收推送ca55e79。M2重修申请、双级审核、开班选课、名册、课表与冲突检测已于2026-11-28通过用户验收，授权提交推送codex/m2-retake-workflow。接下来独立开发M3缓考安排、重修成绩录入与归档。

## 技术方案

用户已确认采用FastAPI，详见[AI扩展与技术选型](docs/08-ai-and-stack-decision.md)。当前M2开发版为0.3.0，演示业务规则已确认可先推进。

- 后端：Python 3.12+、FastAPI、Pydantic、SQLAlchemy 2、Alembic、Uvicorn。
- 前端：Vue 3、TypeScript、Vite、Element Plus。
- 数据库：当前本地运行MySQL 8.0.36，已从SQLite同步原有数据并通过Alembic迁移；保留SQLite作为便携开发和回归测试选项。
- 会话：同源 HttpOnly Cookie + CSRF 防护；服务端校验角色、归属与审核节点。
- 依赖：uv管理Python环境并提交uv.lock；npm依赖由package-lock.json锁定。

## 本地启动

在项目根目录打开两个PowerShell终端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Target backend
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Target frontend
```

打开 http://127.0.0.1:5173/；学生20240001、教师teacher01、院系dept01、校教务admin，演示密码均为`Demo@2026`。API交互文档 http://127.0.0.1:8080/docs ，完整流程见验收清单。

## 文档入口

| 文档 | 内容 |
| --- | --- |
| [需求规格](docs/01-requirements.md) | 需求编号、权限、规则、状态机、智能特性边界 |
| [架构与数据库](docs/02-design.md) | 分层设计、ER 图、数据字典、事务与安全 |
| [接口约定](docs/03-api.md) | 已实现接口、错误码、后续接口规划 |
| [开发与部署](docs/04-development.md) | 环境、启动、MySQL 配置、版本控制约定 |
| [迭代与验收](docs/05-roadmap-acceptance.md) | 里程碑、验收步骤、待确认事项 |
| [测试记录](docs/06-test-report.md) | 自动化与手工验证结果 |
| [论文资料索引](docs/07-thesis-evidence.md) | 需求到实现的证据与论文素材目录 |
| [AI扩展与选型](docs/08-ai-and-stack-decision.md) | FastAPI/Java比较、AI建议与模块边界 |
| [MySQL同步记录](docs/09-mysql-migration.md) | 本地数据库、数据核对、测试隔离与恢复位置 |
| [M2设计与验收](docs/10-m2-retake-design.md) | 重修规则、数据表、接口、并发策略、验收步骤 |
| [M2测试记录](docs/11-m2-test-report.md) | 双数据库回归、浏览器联调、证据及限制 |
| [变更记录](CHANGELOG.md) | 每阶段交付内容及验收状态 |

启动方式、演示账号和验收流程见开发文档与迭代文档。所有演示数据均为虚构数据。请勿上传真实医疗证明到演示环境。
