FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w -buildid=" -o /updater .

FROM scratch
COPY --from=build /updater /updater
USER 0:0
EXPOSE 8090
ENTRYPOINT ["/updater"]
