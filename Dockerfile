FROM alpine:3.10

COPY scripts/docker-install-system.sh /tmp/
RUN /tmp/docker-install-system.sh

COPY scripts/docker-install-project.sh pyproject.toml poetry.lock /tmp/
RUN /tmp/docker-install-project.sh

COPY . /src
WORKDIR /src

EXPOSE 22
CMD make realprod
