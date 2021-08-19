#!/usr/bin/env bash

export ARLO_AUDITADMIN_AUTH0_BASE_URL="https://votingworks-noauth.herokuapp.com"
export ARLO_JURISDICTIONADMIN_AUTH0_BASE_URL="https://votingworks-noauth.herokuapp.com"
export ARLO_AUDITADMIN_AUTH0_CLIENT_ID="test"
export ARLO_JURISDICTIONADMIN_AUTH0_CLIENT_ID="test"
export ARLO_AUDITADMIN_AUTH0_CLIENT_SECRET="secret"
export ARLO_JURISDICTIONADMIN_AUTH0_CLIENT_SECRET="secret"
export ARLO_SESSION_SECRET="secret"
export ARLO_HTTP_ORIGIN="http://localhost:3000"

export FLASK_ENV=${FLASK_ENV:-development}
trap 'kill 0' SIGINT SIGHUP
cd "$(dirname "${BASH_SOURCE[0]}")"

poetry run python -m server.main &
yarn --cwd client start