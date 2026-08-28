"""El límite sobre la emisión de API keys.

`POST /v1/api-keys` es la única ruta pública de escritura del servidor y, mientras el
correo no se verifique, también un primitivo de **revocación remota**: pedir una key para
un correo ajeno revoca la suya. Un límite ahí no es higiene, es lo que hace que el abuso
se vea en vez de inferirse.

Es independiente de #22, que limitará por credencial: aquí todavía no hay ninguna, y ese
es justamente el problema.

**El límite es por proceso**, como el caché del verificador. Con varios workers el tope
real se multiplica por su número. Se dice en docs/api-keys.md; el día que eso no alcance,
la cuenta se lleva al registro, que ya es la base compartida.
"""

import logging
import time
from collections import deque
from functools import lru_cache
from typing import Callable

from indicadores_sieej.config import Settings, settings
from indicadores_sieej.errors import RateLimited

log = logging.getLogger(__name__)

HOUR_S = 3600
DAY_S = 86400

# A partir de aquí se barren todas las IPs y no solo la que consulta. El barrido es O(n) y
# no hace falta en operación normal: existe para que una ráfaga desde muchas direcciones
# no deje el diccionario creciendo sin techo.
SWEEP_AT = 10_000


class IssueLimiter:
    """Ventana deslizante por IP, más un tope diario del servidor entero.

    El tope diario no es redundante: el de la IP frena a un origen, y una botnet no es un
    origen. Con los dos, el peor caso es acotado sin depender de cuántas direcciones tenga
    quien insiste.
    """

    def __init__(self, cfg: Settings, clock: Callable[[], float] = time.monotonic):
        self.per_ip_hour = cfg.api_key_issue_per_ip_hour
        self.per_day = cfg.api_key_issue_per_day
        self.clock = clock
        self._by_ip: dict[str, deque[float]] = {}
        self._today: deque[float] = deque()

    def check(self, ip: str) -> None:
        """Cuenta esta solicitud, o levanta `RateLimited` si ya no cabe.

        La IP se registra **solo cuando el límite se dispara**, y en `WARNING`: es dato
        personal, y en el camino normal no aporta nada que no aporte el conteo.
        """
        now = self.clock()
        self._sweep(now)

        recent = self._by_ip.setdefault(ip, deque())
        _drop_before(recent, now - HOUR_S)
        if len(recent) >= self.per_ip_hour:
            log.warning("emisión de API keys: %s alcanzó su límite por hora", ip)
            raise RateLimited("demasiadas solicitudes de API key desde este origen; intenta más tarde")

        if len(self._today) >= self.per_day:
            log.warning("emisión de API keys: tope diario del servidor alcanzado; última solicitud de %s", ip)
            raise RateLimited("el servidor alcanzó su tope de emisión de API keys por hoy; intenta más tarde")

        recent.append(now)
        self._today.append(now)

    def _sweep(self, now: float) -> None:
        _drop_before(self._today, now - DAY_S)
        if len(self._by_ip) < SWEEP_AT:
            return
        for ip, seen in list(self._by_ip.items()):
            _drop_before(seen, now - HOUR_S)
            if not seen:
                del self._by_ip[ip]


def _drop_before(seen: deque[float], cutoff: float) -> None:
    while seen and seen[0] <= cutoff:
        seen.popleft()


@lru_cache(maxsize=1)
def issue_limiter() -> IssueLimiter:
    """El limitador del proceso. **Uno solo**, como el verificador."""
    return IssueLimiter(settings())
