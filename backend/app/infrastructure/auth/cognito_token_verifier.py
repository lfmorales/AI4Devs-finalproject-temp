from app.config import TokenIssuer
from app.infrastructure.auth.issuer_token_verifier import IssuerTokenVerifier, SigningKeyProvider


class CognitoTokenVerifier(IssuerTokenVerifier):
    """Verifies Cognito ID tokens against the User Pool's JWKS.

    Kept with its constructor of today so the wiring in providers.py does not change; the
    composite verifier task replaces it with an IssuerTokenVerifier built from the settings.
    """

    def __init__(
        self,
        region: str,
        user_pool_id: str,
        client_id: str,
        jwks_client: SigningKeyProvider | None = None,
    ) -> None:
        issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        super().__init__(
            TokenIssuer(
                kind="cognito",
                issuer=issuer,
                audience=client_id,
                jwks_url=f"{issuer}/.well-known/jwks.json",
                user_claim="sub",
                required_scope=None,
            ),
            jwks_client,
        )
