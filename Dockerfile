ARG PYTHON_VERSION=3.11-alpine

FROM python:${PYTHON_VERSION}

RUN apk add py3-virtualenv py3-pytest python3-dev gcc musl-dev openldap-dev

RUN virtualenv /.venv
ENV VIRTUAL_ENV /.venv
ENV PATH /.venv/bin:$PATH

RUN adduser -D user

RUN chown -R user:user /.venv

USER user

ADD requirements.txt .
ADD requirements-minimal.txt .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

WORKDIR /app