import os
import jwt
from pwdlib import PasswordHash
from typing import Annotated
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, StringConstraints
from datetime import datetime, timedelta, timezone
from threading import Lock

app = FastAPI(title="NetPulse Devices API")

TRAINING_USERNAME = os.getenv("NETPULSE_USERNAME")
plain_password = os.environ.pop("NETPULSE_PASSWORD", None)
JWT_SECRET = os.getenv("NETPULSE_JWT_SECRET")

if not TRAINING_USERNAME or not plain_password or not JWT_SECRET:
    raise RuntimeError(
        "Set NETPULSE_USERNAME, NETPULSE_PASSWORD, and NETPULSE_JWT_SECRET"
    )

password_hash = PasswordHash.recommended()
TRAINING_PASSWORD_HASH = password_hash.hash(plain_password)
del plain_password

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)

class HomeResponse(BaseModel):
    message: str
    documentation: str
    public_devices: str

class DeviceWrite(BaseModel):
    name: NonEmptyText
    device_type: NonEmptyText
    status: NonEmptyText
    location: NonEmptyText


class Device(DeviceWrite):
    id: int


class DevicePatch(BaseModel):
    name: NonEmptyText | None = None
    device_type: NonEmptyText | None = None
    status: NonEmptyText | None = None
    location: NonEmptyText | None = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

devices: dict[int, Device] = {
    1: Device(
        id=1,
        name="Core Router",
        device_type="router",
        status="online",
        location="Mumbai",
    ),
    2: Device(
        id=2,
        name="Office Switch",
        device_type="switch",
        status="offline",
        location="Pune",
    ),
}

device_lock = Lock()
next_device_id = max(devices, default=0) + 1

@app.get("/", response_model=HomeResponse,include_in_schema=False)
def home() -> HomeResponse:
    return HomeResponse(
        message="Welcome to the NetPulse Devices API. Explore devices or use the API documentation to manage them.",
        documentation="/docs",
        public_devices="/devices",
    )

@app.get("/devices", response_model=list[Device])
def list_devices() -> list[Device]:
    with device_lock:
        return list(devices.values())


@app.get("/devices/{device_id}", response_model=Device)
def get_device(device_id: int) -> Device:
    with device_lock:
        device = devices.get(device_id)

    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    return device

@app.post("/auth/token", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    valid_user = form_data.username == TRAINING_USERNAME
    valid_password = password_hash.verify(
        form_data.password, TRAINING_PASSWORD_HASH
    )

    if not valid_user or not valid_password:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    token = jwt.encode(
        {"sub": TRAINING_USERNAME, "exp": expires_at},
        JWT_SECRET,
        algorithm="HS256",
    )

    return TokenResponse(access_token=token, token_type="bearer")


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> str:
    authentication_error = HTTPException(
        status_code=401,
        detail="Invalid or missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise authentication_error

    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.InvalidTokenError as exc:
        raise authentication_error from exc

    if claims["sub"] != TRAINING_USERNAME:
        raise authentication_error

    return TRAINING_USERNAME

@app.post(
    "/devices",
    response_model=Device,
    status_code=201,
    dependencies=[Depends(get_current_user)],
)
def create_device(payload: DeviceWrite) -> Device:
    global next_device_id

    with device_lock:
        device = Device(id=next_device_id, **payload.model_dump())
        devices[next_device_id] = device
        next_device_id += 1

    return device


@app.put(
    "/devices/{device_id}",
    response_model=Device,
    dependencies=[Depends(get_current_user)],
)
def replace_device(device_id: int, payload: DeviceWrite) -> Device:
    with device_lock:
        if device_id not in devices:
            raise HTTPException(status_code=404, detail="Device not found")

        replacement = Device(id=device_id, **payload.model_dump())
        devices[device_id] = replacement

    return replacement


@app.patch(
    "/devices/{device_id}",
    response_model=Device,
    dependencies=[Depends(get_current_user)],
)
def update_device(device_id: int, payload: DevicePatch) -> Device:
    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(status_code=422, detail="Provide a field to update")

    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Fields cannot be null")

    with device_lock:
        device = devices.get(device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")

        updated_data = device.model_dump()
        updated_data.update(changes)
        updated_device = Device.model_validate(updated_data)
        devices[device_id] = updated_device

    return updated_device

@app.delete(
    "/devices/{device_id}",
    status_code=204,
    dependencies=[Depends(get_current_user)],
)
def delete_device(device_id: int) -> None:
    with device_lock:
        if device_id not in devices:
            raise HTTPException(status_code=404, detail="Device not found")

        del devices[device_id]