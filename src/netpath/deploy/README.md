# Host an iperf3 server in your ASN

netpath measures real cross-ASN throughput only when it can find an iperf3
server *inside* the target network. Public coverage is sparse — hosting one
takes a single command, and these assets handle the rest: keeping it running
and making it discoverable.

Every asset here is also available from any netpath install via
`netpath serve --emit <systemd|docker|compose|cloud-init|install|registry>`.

## 1. Run the server

Pick whichever fits your environment (all serve `iperf3 -s` on TCP/UDP 5201):

**Already have netpath on the box**

```sh
netpath serve                      # runs iperf3 -s and registers it locally
```

**Bare metal / VM with systemd**

```sh
sudo sh install.sh                 # installs iperf3 + hardened systemd unit
# or: netpath serve --emit install | sudo sh
```

**Docker**

```sh
docker compose up -d               # uses the Dockerfile in this directory
```

**Fresh cloud VM**

Pass `cloud-init.yaml` as user-data when creating the instance.

Then open **TCP and UDP 5201** in your firewall / security group. iperf3
serves one test at a time; that is fine for measurement use.

## 2. Make it discoverable

Run `netpath serve --setup-only` on (or for) the server — it detects the
public IP and ASN, writes the local registry entry, and prints everything
below ready to use. The options, from private to public:

| Mechanism | Who finds it | How |
|---|---|---|
| Local registry | you | `~/.netpath/servers.json` (written by `netpath serve`) |
| Shared list URL | your org/community | host the JSON anywhere; users set `NETPATH_SERVERS_URL=https://…` |
| Community registry | registry subscribers | `netpath serve --announce https://registry…/register` (see `registry.py`) |
| DNS SRV record | anyone probing your domain | publish `_netpath-iperf3._tcp.example.com. 3600 IN SRV 0 0 5201 iperf.example.com.` — `netpath host example.com --throughput` finds it automatically |
| Public list | everyone | submit to <https://github.com/R0GGER/public-iperf3-servers>; every netpath install checks it |

## 3. Optional: run a community registry

`registry.py` is a stdlib-only reference registry that accepts
`netpath serve --announce` submissions (TCP-verifying each claimed server)
and serves them in the schema netpath already consumes:

```sh
python3 registry.py --port 8080 --store /var/lib/netpath-registry/servers.json
```

Front it with a TLS-terminating reverse proxy and rate-limit `/register`
there. Consumers point `NETPATH_SERVERS_URL` at its base URL.
