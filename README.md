# secure-netpulse-devices-api

# NetPulse Devices API

A small FastAPI service for managing devices in memory. Anyone can read devices. Creating, replacing, updating, and deleting devices requires a JWT bearer token.

## Setup

Activate the project's virtual environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

```bash
python -m pip install -r requirements.txt
```

Set the local training credential and signing secret in the terminal that will run the API:

```bash
export NETPULSE_USERNAME=trainer
read -r -s -p "Training password: " NETPULSE_PASSWORD
export NETPULSE_PASSWORD
printf '\n'
export NETPULSE_JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

Start the server:

```bash
python -m uvicorn main:app --reload
```

Open the Swagger UI at http://127.0.0.1:8000/docs.

## API

| Method | Endpoint | Access | Success |
|---|---|---|---|
| POST | `/auth/token` | Public | 200, bearer token |
| GET | `/devices` | Public | 200, device list |
| GET | `/devices/{device_id}` | Public | 200, device |
| POST | `/devices` | Bearer token | 201, created device |
| PUT | `/devices/{device_id}` | Bearer token | 200, replaced device |
| PATCH | `/devices/{device_id}` | Bearer token | 200, updated device |
| DELETE | `/devices/{device_id}` | Bearer token | 204, no body |

Send the training username and password as form fields to `/auth/token`. For write requests, send the returned token in the `Authorization: Bearer <token>` header. Tokens expire after 30 minutes.

A device has `id`, `name`, `device_type`, `status`, and `location`. POST and PUT require all editable fields. PATCH accepts selected fields and leaves omitted fields unchanged.

## Storage and errors

The API starts with two devices. Data is stored in memory and resets when the application restarts. Missing devices return 404. Missing or invalid bearer tokens and invalid login credentials return 401.

## Security scope

The training password is hashed when the application starts. Credentials and the JWT signing secret come from environment variables. Bearer tokens require HTTPS outside this local lab. Authentication does not provide per-user authorization rules.


## Security review

- [x] The training username, password, and JWT signing secret come from environment variables.
- [x] No real password, signing secret, or bearer token appears in source code.
- [x] The training password is hashed before it is kept in application memory.
- [x] Login issues a JWT only for valid credentials, with `subject` and `expiration` claims.
- [x] Token validation checks the signature, expiry, and configured training user.
- [x] GET endpoints are public; POST, PUT, PATCH, and DELETE require a bearer token.
- [x] Missing and invalid tokens, and invalid login credentials, return 401.
- [x] Bearer tokens would require HTTPS outside this local lab.
- [x] Authentication does not yet provide per-device authorization.

## Verification

With the virtual environment active and the three NETPULSE environment variables set, run:

```bash
python verify_jwt.py
python verify_contract.py
```

The JWT check covers a valid subject, an unrelated subject, expiry, and a wrong signature. The HTTP check starts a temporary local server and verifies 24 public, protected, error, validation, and CRUD cases. Both checks passed with zero failures on 11 November 2026. Neither script prints a password, signing secret, or bearer token.
