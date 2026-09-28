#!/usr/bin/env python3
"""
Persona login + invoke helper for the governed Runtime (JWT path).

Logs in to Cognito as a persona (USER_PASSWORD_AUTH), then invokes the runtime
over HTTPS with the ID token as a Bearer — the identity the runtime's JWT
authorizer validates and the entrypoint reads custom:tenant/custom:role from.

Usage:
  export POOL_ID=... CLIENT_ID=... RUNTIME_ARN=... [PERSONA_PW=...]
  python persona_invoke.py analyst-a "how many trips"
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
POOL = os.environ["POOL_ID"]
CID = os.environ["CLIENT_ID"]
ARN = os.environ["RUNTIME_ARN"]
PW = os.environ.get("PERSONA_PW", "DuckDbGov2026!")

_idp = boto3.client("cognito-idp", region_name=REGION)
_SECRET = _idp.describe_user_pool_client(
    UserPoolId=POOL, ClientId=CID)["UserPoolClient"].get("ClientSecret")


def _secret_hash(user: str) -> str:
    return base64.b64encode(
        hmac.new(_SECRET.encode(), (user + CID).encode(), hashlib.sha256).digest()
    ).decode()


def login(user: str) -> str:
    params = {"USERNAME": user, "PASSWORD": PW}
    if _SECRET:
        params["SECRET_HASH"] = _secret_hash(user)
    return _idp.initiate_auth(ClientId=CID, AuthFlow="USER_PASSWORD_AUTH",
                              AuthParameters=params)["AuthenticationResult"]["IdToken"]


def invoke(token: str, prompt: str) -> str:
    url = (f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/"
           f"{urllib.parse.quote(ARN, safe='')}/invocations?qualifier=DEFAULT")
    req = urllib.request.Request(
        url, data=json.dumps({"prompt": prompt}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json",
                 "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": secrets.token_hex(20)})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


if __name__ == "__main__":
    user = sys.argv[1] if len(sys.argv) > 1 else "analyst-a"
    prompt = " ".join(sys.argv[2:]) or "how many trips"
    print(invoke(login(user), prompt))
