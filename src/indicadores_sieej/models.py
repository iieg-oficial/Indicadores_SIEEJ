from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

# Tipos permitidos para los parámetros de un indicador y su equivalente en Python.
TYPES = {"str": str, "int": int}


class Coverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geografica: str
    temporal: str


class Parameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str
    tipo: Literal["str", "int"]
    requerido: bool = False
    descripcion: str


class Indicator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    nombre: str
    tema: str
    definicion: str
    unidad: str
    fuente: str
    pipeline: str
    origen: str
    nivel: Literal["nacional", "estatal", "municipal"]
    periodicidad: str
    cobertura: Coverage
    notas: Optional[str] = None
    parametros: list[Parameter] = []
    sql: str

    def metadata(self) -> dict:
        """Metadata sin el SQL, que es lo único que se expone a un agente."""
        return self.model_dump(exclude={"sql"})
