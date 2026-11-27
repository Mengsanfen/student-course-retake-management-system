# AI扩展与后端技术选型

日期：2026-11-27；状态：用户已明确选择“切换到FastAPI”。演示业务规则已确认可先推进。当前采用FastAPI + Vue 3 + TypeScript + Element Plus，正式数据库目标MySQL。

## 1. 当前状态与建议

FastAPI M1已接替Spring Boot原型；Vue和/api/v1业务契约保留。Python服务、迁移和集成测试已重写。尚未用户验收、commit或push。旧Java源码及测试记录已作本地忽略归档，不再作为当前开发方案。

| 维度 | FastAPI / Python | Spring Boot / Java |
| --- | --- | --- |
| 调用大模型接口 | Python客户端或HTTP | Java客户端或HTTP、Spring AI |
| 本地模型、数据处理和实验 | 可直接复用Python库和实验代码 | 可调用Python服务，增加进程/服务边界 |
| API交互文档 | 内置OpenAPI/Swagger UI | 可引入对应组件 |
| 事务、权限、迁移 | 已实现SQLAlchemy事务、RBAC、Alembic、会话安全 | 旧原型使用Security、JDBC事务、Flyway |
| 当前状态 | 已确认并实施，重新回归测试 | 仅保留本地归档 |

决策依据：用户后续可能做Python数据分析或本地AI，且主动确认Python方向，故采用FastAPI。Java也能调用模型接口，不以“Java无法加AI”为迁移理由。FastAPI不是AI模型；效果依赖模型、知识来源和验证方法。

Python方案保留认证、CSRF、数据范围、状态机、数据库并发和材料安全。当前使用SQLAlchemy 2、Alembic、Pydantic、pytest/httpx，具体版本见uv.lock。尚未接入真实AI模型，AI功能待老师确认。

## 2. 建议AI范围

优先与老师确认“校规与办事指南问答”：从学校授权的制度文档检索条款，回答附出处、条款和版本；无依据时说明无法确定并转教务咨询。真实知识库依赖学校资料，当前不编造校规。

可选扩展为学情简报：使用已计算的院系/课程聚合指标生成摘要，显示统计范围、口径和生成标识。数值由查询计算。

资格、冲突、时限继续采用可解释规则；申请批准和成绩归档由确定性业务与授权人员处理。AI不直接修改审批、成绩或权限。个人证明材料不默认发送给外部模型，初期知识库限公开或授权制度资料。

## 3. 架构与评估

业务服务 → AI适配接口 → 可替换模型提供方。密钥服务端环境配置，设置超时、输入限制和调用上限。AI故障仅影响辅助问答，不影响申请审核；身份、资格和状态机不降级。

评估集包含制度问题、无依据问题、引用准确性、越权问题、提示注入。记录模型/知识库版本、引用、延迟与人工评分。

## 4. 官方依据

- FastAPI功能与OpenAPI：https://fastapi.tiangolo.com/features/
- Spring AI模型、向量库、工具及RAG：https://docs.spring.io/spring-ai/reference/api/

官方能力已于2026-11-27核对。生态衔接便利性和推荐是基于项目范围的工程判断，具体AI功能仍待老师确认。
