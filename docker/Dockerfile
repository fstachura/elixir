FROM debian:bookworm

RUN \
  apt-get update && \
  apt-get --no-install-recommends -y install \
    python3 \
    python3-pip \
# TODO switch to berkeleydb
# NOTE this doesn't easily install from pypi
    python3-bsddb3 \
    python3-venv \
    universal-ctags \
    perl \
    git \
    apache2 \
    libapache2-mod-wsgi-py3 \
    libjansson4 \
    libyaml-0-2 \
    wget

COPY . /usr/local/elixir/

WORKDIR /usr/local/elixir/
RUN python3 -m venv --system-site-packages venv && \
    . ./venv/bin/activate && \
    pip install -r requirements.txt

RUN mkdir -p /srv/elixir-data/

# apache elixir config, see elixir README
# make apache less stricter about cgitb spam headers
COPY ./docker/000-default.conf /etc/apache2/sites-available/000-default.conf

RUN a2enmod cgi rewrite

EXPOSE 80

ENTRYPOINT ["/usr/sbin/apache2ctl", "-D", "FOREGROUND"]
