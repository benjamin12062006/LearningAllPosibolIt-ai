"""Credenciales de Google en Vercel, sin claves (deploys, bitácora 07).

En un contenedor de Vercel el token OIDC llega solo en la cabecera
`x-vercel-oidc-token` de cada petición: no hay variable ni archivo (comprobado el
2026-11-20 con un contenedor de prueba). El middleware guarda el último token y
Google lo cambia por un acceso temporal de la cuenta de servicio `ktsu-ai`.
Cada token dura dos horas y cada petición trae uno nuevo.
"""

from typing import Final

from google.auth import exceptions, external_account, identity_pool
from google.auth.transport import Request

from ktsu_ai.config.configuration import GoogleFederationConfiguration

CLOUD_PLATFORM_SCOPE: Final = "https://www.googleapis.com/auth/cloud-platform"
JWT_TOKEN_TYPE: Final = "urn:ietf:params:oauth:token-type:jwt"
GOOGLE_STS_URL: Final = "https://sts.googleapis.com/v1/token"


class LatestVercelOidcToken(identity_pool.SubjectTokenSupplier):
    """El último token OIDC que trajo una petición."""

    def __init__(self) -> None:
        self._token: str | None = None

    def remember(self, token: str) -> None:
        self._token = token

    def get_subject_token(
        self, context: external_account.SupplierContext, request: Request
    ) -> str:
        if self._token is None:
            # Solo pasa si algo llama a Google antes de recibir ninguna petición.
            # google-auth no tiene anotaciones de tipos en sus excepciones.
            raise exceptions.RefreshError(  # type: ignore[no-untyped-call]
                "Todavía no ha llegado ningún token OIDC de Vercel."
            )
        return self._token


def create_vercel_federated_credentials(
    config: GoogleFederationConfiguration, token: LatestVercelOidcToken
) -> identity_pool.Credentials:
    pool = (
        f"projects/{config.project_number}/locations/global"
        f"/workloadIdentityPools/{config.pool_id}"
    )
    # google-auth no anota el constructor de las credenciales externas.
    return identity_pool.Credentials(  # type: ignore[no-untyped-call]
        audience=f"//iam.googleapis.com/{pool}/providers/{config.provider_id}",
        subject_token_type=JWT_TOKEN_TYPE,
        token_url=GOOGLE_STS_URL,
        subject_token_supplier=token,
        service_account_impersonation_url=(
            "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
            f"{config.service_account_email}:generateAccessToken"
        ),
        scopes=[CLOUD_PLATFORM_SCOPE],
    )
