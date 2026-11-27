# 开发、运行与部署手册

## 1. 环境

Python 3.12+、uv、Node 22.12+或24、npm。无需Java或Maven。uv管理项目内`backend/.venv`；首次启动可设置PROJECT_PYTHON为Python解释器绝对路径。脚本依次使用该变量、现有虚拟环境、Codex附带Python或uv的Python 3.12选择机制，不更改系统环境。

后端依赖由`backend/pyproject.toml`定义、`backend/uv.lock`锁定；执行uv sync --locked保证一致。前端锁文件为package-lock.json，首次安装需要PyPI/npm网络。uv安装见https://docs.astral.sh/uv/getting-started/installation/ 。依赖缓存放在项目`.runtime`且Git忽略；不提交虚拟环境、缓存、数据库、会话或材料。

## 2. 本地启动（PowerShell）

项目根目录打开两个终端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Target backend
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Target frontend
```

前端http://127.0.0.1:5173，后端http://127.0.0.1:8080。启动脚本仅在缺少node_modules时执行npm ci；依赖更新后手动npm ci。前端`/api`由Vite代理到8080，确保Cookie同源与CSRF正常工作。端口占用时先检查对应进程，不能随意终止未知服务。

后端开发脚本执行锁定依赖安装、Alembic upgrade和演示种子初始化，再启动Uvicorn。该脚本仅供本地演示，会设置DEMO_MODE=true。空库首次生成虚构数据；演示密码统一`Demo@2026`，可在首次建库前设置DEMO_PASSWORD（8–72个UTF-8字节）。变量变化不重置已有密码。

交互文档：http://127.0.0.1:8080/docs；OpenAPI：http://127.0.0.1:8080/openapi.json。生产可限制文档访问。认证请求依赖Cookie和X-CSRF-TOKEN，登录前后分别GET /api/v1/auth/csrf，不能只在Swagger中填写用户名而忽略CSRF。

| 角色 | 账号 |
| --- | --- |
| 学生（主验收） | 20240001 |
| 另一学生（隔离验证） | 20240002 |
| 另一院系学生 | 20240003 |
| 任课教师（数据结构、数据库） | teacher01 |
| 另一任课教师（计算机网络） | teacher02 |
| 本院教务 | dept01 |
| 另一院系教务 | dept02 |
| 校教务 | admin |

当前连接本机MySQL 8.0.36的`retake_management`数据库，由忽略的`backend/.env`配置。使用仅限127.0.0.1及项目数据库权限的retake_app账号，root密码不保存在项目中。原SQLite库`backend/.data/retake.sqlite3`、迁移前备份和旧H2文件均保留。材料仍在`backend/.uploads`，路径未变。会话固定有效期默认30分钟，可用SESSION_MINUTES配置；演示考试时间保留首次初始化值。不要删除数据库“解决”迁移错误。

## 3. 检查与构建

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

后端执行pytest/httpx集成测试；前端执行vue-tsc和Vite构建。默认测试使用`.runtime/pytest-fastapi-tmp`下SQLite文件与临时材料，不修改业务库。每次运行会重建专用临时目录，不能存放人工资料。加`-Database mysql`只跑MySQL，加`-Database both`分别跑两套；MySQL凭据从忽略的`backend/.env.mysql-test`读取，测试仅接受本机`retake_management_test`库，每个用例前后删除该测试库的业务行，禁止填业务库地址。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -Database both
```

JUnit分别在`.runtime/pytest-fastapi.xml`及`.runtime/pytest-mysql.xml`，摘要见测试记录。测试不能代替用户验收。

独立后端命令（backend内）：`uv run --locked pytest -q`或追加`--database mysql`。默认使用`backend/.runtime`下的临时目录，统一脚本则使用根目录`.runtime`。

## 4. MySQL及部署方案

当前实测MySQL 8.0.36，业务库retake_management采用utf8mb4、utf8mb4_0900_as_cs排序规则及InnoDB。环境变量DATABASE_URL示例：`mysql+pymysql://retake_app:URL_ENCODED_PASSWORD@127.0.0.1:3306/retake_management?charset=utf8mb4`，密码特殊字符须URL编码。`.env.example`提供模板；`.env`和`.env.mysql-test`均忽略，不能提交。生产设置DEMO_MODE=false、UPLOAD_DIR持久目录、COOKIE_SECURE=true，勿运行演示种子。以下命令在backend执行：

```powershell
uv sync --locked --no-dev
uv run --locked --no-dev python -m app.manage upgrade
uv run --locked --no-dev uvicorn app.main:app --host 127.0.0.1 --port 8080
```

反向代理提供HTTPS及前端dist，将/api转发后端，不直接暴露公网。数据库和材料一起备份，暂停写入或使用一致性快照；SQLite必须使用备份API或停服完整备份，不能忽略WAL。本次已使用SQLite备份API并保留原库，导入MySQL后逐列核对。MySQL迁移及并发回归已实测，Docker不是本地MySQL的前提；生产环境完整恢复演练仍待后续进行。

本次迁移过程及恢复位置见09文档。`python -m app.bootstrap_mysql`只供新空环境一次性创建本地项目库并交互输入root密码，遇到已有库/账号或环境文件会停止；不要在当前环境重复运行。`python -m app.sync_database --backup <新备份路径> --report <报告路径>`只向迁移后全空的目标库插入，不会覆盖已有业务数据；它不是双向持续同步工具。

## 5. Git与验收协作

初始检查发现Git根目录位于项目上一级，同时包含另一个项目；本项目目录自身原先没有.git。现已在本目录建立独立仓库，origin仍指向用户提供的远端，分支接续origin/main的初始提交。原上一级仓库未修改。本项目内运行`git rev-parse --show-toplevel`应返回当前项目目录。

用户规则：每完成一个可演示功能阶段 → 自动检查及文档更新 → 用户验收 → 明确通过后commit、push。验收前不提交、不推送。验收阶段推到对应分支，是否合并main由用户决定。

M1已验收并推送提交ca55e79到codex/m1-deferral-workflow。当前M2分支codex/m2-retake-workflow基于该提交开发，M2待验收，未提交推送。未自动合并main。

提交建议：`feat: implement deferral application and approval workflow`。每次只暂存本阶段源码、文档、锁文件和迁移；检查`git diff --cached`，排除密码、数据库、上传材料、缓存和日志。保留原始研究文档作为需求来源；如后续需公开仓库，应由用户确认材料公开范围。

技术栈已按用户确认切换FastAPI。旧Java源码、pom和旧测试说明保留于忽略目录`.runtime/legacy-springboot-0.1`，不参与启动、检查或提交；当前正式后端是backend/app、migrations和tests。旧H2数据未自动迁移，因为仍处于演示阶段；如果将来需要保留旧业务记录，必须另做数据迁移和核对。

## 6. 排错

- Python版本不足：设置`$env:PROJECT_PYTHON='Python 3.12+解释器绝对路径'`再启动脚本；不要使用系统Python 3.11安装本项目依赖。
- 首次依赖下载失败：检查网络/仓库配置，保留原始错误；不随意降低版本或关闭TLS校验。
- 登录403：刷新页面重新获取CSRF；检查前后端是否使用同一域名和Vite代理。
- 有会话但无列表：检查账号所属院系与授课关系，不能为排错扩大权限。
- 考试已过：这是截止规则生效，调整演示开课数据需记录；不能从前端绕过。
- 数据表不存在：在backend执行`uv run --locked python -m app.manage upgrade`，不要用create_all绕过迁移。
- M2数据库版本为0002，开发脚本会升级后幂等添加学期、基础课表及3个演示重修班，不覆盖原有申请、成绩、审核或通知。升级前MySQL备份在.runtime/backups/m1-before-m2.sql。
- 历史0001的SQLite备份不能直接按0002模型导入：先保留原件，在副本上执行迁移，再用同版本源/目标调用同步；版本不一致会拒绝，不覆盖目标数据。
- pytest或esbuild被沙盒限制：保留错误，通过工具授权运行指定检查；不关闭系统安全设置。
