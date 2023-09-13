ARG PYTHON_VERSION=3.11-alpine

FROM python:${PYTHON_VERSION}

RUN apk add py3-virtualenv py3-pytest python3-dev gcc musl-dev openldap-dev bash

ENV VENV /.venv
RUN virtualenv ${VENV}
ENV PATH ${VENV}/bin:$PATH

RUN adduser -D user

WORKDIR /app

ADD . .
RUN chown -R user:user ${VENV} .

USER user

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD ["./run.sh"]