from pydantic import BaseModel, Extra


def _to_camel(s: str) -> str:
    split = s.split("_")
    return split[0].lower() + "".join([w.capitalize() for w in split[1:]])


class LspModel(BaseModel):
    class Config:
        alias_generator = _to_camel
        allow_population_by_field_name = True
        extra = Extra.ignore
