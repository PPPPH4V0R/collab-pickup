# Configuration comes from the environment, never from the code.
# For local runs the values can sit in a .env file (not committed to Git);
# load_dotenv() copies them into the environment and never overrides
# variables that are already set.
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    def __init__(self, env=None):
        env = env or os.environ
        # Required values have no default: a missing one stops the service
        # at startup instead of failing on the first request.
        self.database_url = self._require(env, "DATABASE_URL")
        self.jwt_secret = self._require(env, "JWT_SECRET")

    @staticmethod
    def _require(env, name):
        value = env.get(name)
        if not value:
            raise SystemExit(f"FATAL: {name} is required and unset. "
                             f"Refusing to start with incomplete configuration.")
        return value

    def redacted(self):
        """What we loaded, safe to print: the database host, never the password."""
        return {"database": self.database_url.split("@")[-1],
                "jwt_secret": "***"}


settings = Config()
