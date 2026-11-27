# API接口说明

基础路径`/api/v1`，UTF-8 JSON。除health、CSRF获取、登录外需要会话。登录使用form-urlencoded；上传使用multipart；其他写请求使用JSON。登录与所有写操作都带CSRF头。错误格式`{"code":"RULE_VIOLATION","message":"该课程已出分，不能申请缓考"}`。

后端框架为FastAPI，当前应用版本0.3.0（框架依赖版本见uv.lock）；自动契约见`/openapi.json`，交互文档见`/docs`、`/redoc`。业务接口需要同源会话，登录前后GET csrf取得最新令牌，写接口含X-CSRF-TOKEN。M2接口和样例详见10文档；本篇保留M1接口基线。

## 1. 已实现接口（M1）

| 方法 | 路径 | 权限/请求 | 成功响应 |
| --- | --- | --- | --- |
| GET | /health | 公开 | 200，status/version/backend（FastAPI），检查数据库连通 |
| GET | /auth/csrf | 公开，建立/使用会话 | 200，token/headerName |
| POST | /auth/login | username、password表单，CSRF | 200，轮换会话；失败401 |
| GET | /auth/me | 登录用户 | 200，id/username/displayName/role/departmentId/departmentName |
| POST | /auth/logout | 登录会话及CSRF | 200，会话失效 |
| GET | /courses | 学生本人 | 200，Course数组 |
| POST | /attachments | 学生，file字段 | 201，id/originalName/sizeBytes及Location |
| GET | /attachments/{id} | 上传者或对应申请授权人员 | 200，下载流；no-store；未绑定材料仅上传者可读 |
| POST | /deferrals | 学生，enrollmentId/attachmentId/reason | 201，Detail及Location |
| GET | /deferrals | 自动按角色限定范围 | 200，Page<Application> |
| GET | /deferrals/{id} | 本人/任课教师/本院教务/校教务 | 200，Detail |
| POST | /deferrals/{id}/reviews | 当前节点审核人，decision/comment | 200，更新后的Detail |
| GET | /notifications | 登录者本人 | 200，Page<Notice> |
| POST | /notifications/{id}/read | 通知接收人，CSRF | 204 |

分页参数：`page=1&size=20`；page取1–100000，size取1–100。申请列表可加`pendingOnly=true`；审核人据当前角色取对应待办。排序：申请按createdAt及id倒序，通知按id倒序。分页结果为`{items:[],page:1,size:20,total:0}`。列表不返回密码、存储文件名或其他用户材料地址。

Course：`id`是选课记录ID，用于申请的enrollmentId；另含courseName、courseCode、term、credits、teacherName、examAt、score（null表示未出分）。

Application：id、enrollmentId、attachmentId、attachmentName、courseName、courseCode、studentName、studentNumber、departmentName、term、reason、status、createdAt、updatedAt。

Detail：`{application:Application,approvals:Approval[]}`。Approval含id、stage、reviewerName、decision、comment、createdAt。时间为ISO8601 UTC字符串，客户端按北京时间展示。

Notice：id、title、content、applicationId、retakeApplicationId、isRead、createdAt。applicationId指缓考，retakeApplicationId指重修；前端据对应字段打开详情。客户端显示最近100条，申请列表分页。

## 2. 请求例子

```json
{"enrollmentId":1,"attachmentId":1,"reason":"因身体不适需就医，申请课程缓考并提交相关证明材料。"}
```

```json
{"decision":"REJECT","comment":"证明材料不清晰，请补充后重新提交。"}
```

decision只接受APPROVE或REJECT。REJECT的comment不可为空；comment最多500字。提交理由10–1000字，trim后至少10字。服务端根据身份和当前状态决定下一节点，忽略客户端额外的申请人或目标状态字段。

会话调用顺序：GET csrf → 用返回headerName/token执行登录 → 再GET csrf获取轮换后的令牌 → 调用受保护接口。浏览器自动带同源Cookie；客户端不保存密码或会话令牌到localStorage。CSRF失效时提示刷新，不自动重试业务写操作。

## 3. 状态码和业务错误

| HTTP | code | 含义 |
| --- | --- | --- |
| 400 | VALIDATION_ERROR / INVALID_REQUEST | 格式、字段长度、枚举、必填或分页参数错误 |
| 401 | UNAUTHENTICATED / BAD_CREDENTIALS | 未登录、会话失效或账号密码错误 |
| 403 | FORBIDDEN | 角色、数据归属或CSRF校验不通过 |
| 404 | NOT_FOUND | 记录不存在，或通知不属于本人 |
| 409 | STATE_CONFLICT / DATA_CONFLICT | 重复申请、材料复用、错序或并发审核 |
| 413 | FILE_TOO_LARGE | 上传超过配置上限 |
| 422 | RULE_VIOLATION | 资格、截止时间、驳回理由、文件格式等不满足业务条件 |
| 500 | INTERNAL_ERROR | 通用服务错误，服务端日志保留异常信息 |
| 503 | SERVICE_UNAVAILABLE | 数据库操作暂不可用，需重试或联系管理员 |

## 4. M2接口及后续规划

M2已实现：retake-meta、retakes、retakes/{id}、retakes/{id}/reviews、retake-classes、retake-classes/{id}（PATCH）、retake-classes/{id}/conflict-check、retake-enrollments、retake-classes/{id}/students、timetable。权限、输入输出和验收见10文档；OpenAPI同步生成。

M3：exam-arrangements、grade-records、grade-records/{id}/archive。

M4：statistics、reports、alerts、rule-configs、users、courses管理接口。后续接口必须同步补充OpenAPI、数据范围、幂等约束和验收用例。
