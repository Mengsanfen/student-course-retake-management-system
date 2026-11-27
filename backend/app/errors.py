class BusinessError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def forbidden() -> BusinessError:
    return BusinessError(403, "FORBIDDEN", "无权访问该数据或执行此操作")


def missing() -> BusinessError:
    return BusinessError(404, "NOT_FOUND", "记录不存在")


def invalid(message: str) -> BusinessError:
    return BusinessError(422, "RULE_VIOLATION", message)


def conflict(message: str) -> BusinessError:
    return BusinessError(409, "STATE_CONFLICT", message)
