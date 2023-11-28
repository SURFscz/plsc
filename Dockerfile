FROM python:3.8-slim-bookworm

# Do an initial clean up and general upgrade of the distribution
ENV DEBIAN_FRONTEND noninteractive
RUN apt clean && apt autoclean && apt update
RUN apt -y upgrade && apt -y dist-upgrade

# Install the packages we need
RUN apt install -y build-essential libldap2-dev libsasl2-dev git

# Clean up
RUN apt autoremove -y && apt clean && apt autoclean && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

# Create pyff dir
#RUN virtualenv /opt/pyff
# RUN git clone -b main https://github.com/SURFscz/plsc.git /opt/plsc
ADD . .

# Copy process script
COPY misc/process.sh /opt/plsc/process.sh
RUN chmod 755 /opt/plsc/process.sh

# Set the default workdir
WORKDIR /opt/plsc

RUN pip install -r requirements.txt

# Copy entrypoint
COPY ./conf/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/opt/plsc/process.sh"]
