ARG PYTHON_VERSION=3.11-alpine

FROM python:${PYTHON_VERSION}

RUN apk add py3-virtualenv py3-pytest python3-dev gcc musl-dev openldap-dev

WORKDIR /app

ADD requirements.txt .
ADD requirements-minimal.txt .

RUN virtualenv .venv
ENV VIRTUAL_ENV /app/.venv
ENV PATH /app/.venv/bin:$PATH

RUN pip install --upgrade pip
RUN pip install -r requirements.txt
