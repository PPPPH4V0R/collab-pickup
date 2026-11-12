# Authentication: password hashing, issuing and verifying JWTs, and the
# two FastAPI dependencies that guard routes: current_user (WHO is calling,
# else 401) and require_role (WHAT they may do, else 403).
# Per-user rules ("only your own orders") are NOT here: they are enforced
# in the service layer, which looks orders up by id AND owner.
import datetime
import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings

ISSUER = "collab-pickup"
AUDIENCE = "collab-pickup-api"
ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 15 * 60


class AuthError(Exception):
    """401 (who are you?) or 403 (you may not); api.py maps the code."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message, self.details = code, message, {}


class User:
    """The caller, as proven by a verified token."""
    def __init__(self, id, role):
        self.id, self.role = id, role


# ---------- passwords ----------

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password, password_hash):
    # bcrypt only accepts up to 72 bytes and raises on longer input; no
    # stored password is that long, so a longer one is simply wrong.
    if len(password.encode()) > 72:
        return False
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ---------- tokens ----------

def issue(user_id, role):
    """A signed claim: who (sub), what they may do (role), who issued it
    (iss), who it is for (aud), and when it dies (exp)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": user_id, "role": role,
              "iat": now, "exp": now + datetime.timedelta(seconds=TOKEN_TTL_SECONDS)}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def verify(token):
    """Check signature, algorithm, issuer, audience and expiry.
    The algorithm is pinned: a token never chooses how it is verified,
    so an 'alg: none' token is rejected."""
    return jwt.decode(token, settings.jwt_secret,
                      algorithms=[ALGORITHM],
                      issuer=ISSUER,
                      audience=AUDIENCE,
                      options={"require": ["exp", "iat", "iss", "aud", "sub", "role"]})


# ---------- route guards ----------

bearer = HTTPBearer(auto_error=False)      # also adds the "Authorize" button to /docs


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise AuthError("UNAUTHENTICATED", "A bearer token is required.")
    try:
        claims = verify(credentials.credentials)
    except jwt.InvalidTokenError as err:
        raise AuthError("INVALID_TOKEN", f"The token was rejected ({type(err).__name__}).")
    return User(claims["sub"], claims["role"])


def require_role(role):
    def check(user: User = Depends(current_user)):
        if user.role != role:
            raise AuthError("FORBIDDEN", f"This operation requires the '{role}' role.")
        return user
    return check
