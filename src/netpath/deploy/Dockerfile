FROM alpine:3.24
RUN apk add --no-cache iperf3
USER nobody
EXPOSE 5201/tcp 5201/udp
ENTRYPOINT ["iperf3", "-s", "-p", "5201"]
