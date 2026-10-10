"""Optional metadata; never grants permission for real broker execution."""
from pydantic import BaseModel,Field,ConfigDict
class ExecutionLink(BaseModel):
    model_config=ConfigDict(extra="forbid")
    cycle_id:str=Field(min_length=1,max_length=100)
    step_id:str=Field(min_length=1,max_length=160)
    revision:int=Field(ge=1)
