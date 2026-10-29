"""请求体模型。

只做“字段存在、类型正确、长度非空”这一层校验；
业务规则（密码长度、角色取值、状态流转）仍由服务层负责。
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50, description="用户名")
    password: str = Field(min_length=1, description="明文密码（只在登录时传输）")


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, description="至少 6 位，由服务层校验")
    role: str = Field(description="admin / staff / viewer")


class UserRoleUpdateRequest(BaseModel):
    role: str = Field(description="新的角色：admin / staff / viewer")


class MaterialCreateRequest(BaseModel):
    material_code: str = Field(description="资料编号，唯一")
    title: str = Field(description="资料名称")
    modality: str = Field(description="影像检查类型，如 CT、MR、DR、US")
    body_part: str = Field(description="检查部位")
    material_type: str = Field(description="资料载体，如胶片、光盘、纸质报告")
    storage_location: str = Field(description="存放位置")


class MaterialUpdateRequest(BaseModel):
    """只传需要修改的字段，其余保持原值。"""

    title: str | None = None
    modality: str | None = None
    body_part: str | None = None
    material_type: str | None = None
    storage_location: str | None = None


class MaterialImportRow(BaseModel):
    material_code: str | None = None
    title: str | None = None
    modality: str | None = None
    body_part: str | None = None
    material_type: str | None = None
    storage_location: str | None = None


class MaterialImportRequest(BaseModel):
    rows: list[MaterialImportRow] = Field(
        min_length=1,
        max_length=500,
        description="CSV 解析后的资料行，最多 500 行",
    )


class BorrowRequest(BaseModel):
    material_id: int = Field(
        gt=0,
        le=9223372036854775807,
        description="要借阅的资料 id",
    )
    due_at: str | None = Field(
        default=None,
        max_length=32,
        description="应还时间，UTC，格式 YYYY-MM-DD HH:MM:SS；不传默认 14 天后",
    )


class LogArchiveRequest(BaseModel):
    before: str = Field(
        min_length=10,
        max_length=32,
        description="归档截止时间，UTC；支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
    )

