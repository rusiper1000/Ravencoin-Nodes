#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ravencoin 네트워크 크롤러 (GitHub Actions용)
=============================================
ravencoin_node_crawler.py를 서버 자동 실행용으로 다듬은 버전입니다.
- 콘솔 출력 대신 docs/data/latest.json 파일로 결과를 저장합니다.
- 국가별 분포뿐 아니라, 핸드셰이크 중 받는 클라이언트 버전(subver)도 함께 집계합니다.
- GitHub Actions 워크플로우(.github/workflows/crawl.yml)가 이 스크립트를 주기적으로 실행하고,
  결과 JSON을 자동으로 커밋/푸시합니다.
"""

import os
import re
import socket
import struct
import hashlib
import time
import random
import json
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# ── 설정 ────────────────────────────────────────────────────────────
MAX_ROUNDS = 8
MAX_WORKERS = 60
CONNECT_TIMEOUT = 20
ADDR_WAIT = 6
NODE_CAP = 8000
STAGGER_MAX = 0.3
OUTPUT_JSON = os.path.join(os.path.dirname(__file__), "docs", "data", "latest.json")
HISTORY_JSON = os.path.join(os.path.dirname(__file__), "docs", "data", "history.json")
NODE_STATS_JSON = os.path.join(os.path.dirname(__file__), "docs", "data", "node_stats.json")
MAX_HISTORY = 400   # 약 4시간마다 1개씩 쌓이므로 400개 ≈ 2개월치
NODE_STATS_RETENTION_DAYS = 60   # 이만큼 오래 안 잡힌 노드는 통계에서 정리

MAGIC = bytes.fromhex("5241564e")   # Ravencoin mainnet magic ("RAVN")
PORT = 8767
DNS_SEEDS = ["seed-raven.ravencoin.org", "seed-raven.bitactivate.com"]
PROTOCOL_VERSION = 70028            # 실제 네트워크가 요구하는 최소 버전 확인됨 (낮으면 OBSOLETE로 거부됨)

# 알려진 안정 노드 (시드 DNS가 불안정할 때를 대비한 보강용)
KNOWN_GOOD_SEEDS = [
    "165.232.147.4", "98.94.236.125", "154.38.163.235", "152.53.127.98",
    "95.111.241.136", "162.55.88.217", "5.161.192.113", "5.196.79.95",
    "159.195.65.196", "213.91.128.133", "5.78.64.99", "18.144.182.93",
]


# ── P2P 메시지 유틸 ──────────────────────────────────────────────────

def checksum(payload: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]


def make_message(command: str, payload: bytes) -> bytes:
    cmd = command.encode("ascii") + b"\x00" * (12 - len(command))
    return MAGIC + cmd + struct.pack("<I", len(payload)) + checksum(payload) + payload


def encode_varint(n: int) -> bytes:
    if n < 0xfd:
        return struct.pack("<B", n)
    elif n <= 0xffff:
        return b"\xfd" + struct.pack("<H", n)
    elif n <= 0xffffffff:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


def read_varint(data: bytes, pos: int):
    first = data[pos]
    pos += 1
    if first < 0xfd:
        return first, pos
    elif first == 0xfd:
        return struct.unpack("<H", data[pos:pos + 2])[0], pos + 2
    elif first == 0xfe:
        return struct.unpack("<I", data[pos:pos + 4])[0], pos + 4
    return struct.unpack("<Q", data[pos:pos + 8])[0], pos + 8


def encode_varstr(s: bytes) -> bytes:
    return encode_varint(len(s)) + s


def net_addr(ip: str, port: int, services: int = 0) -> bytes:
    try:
        packed = socket.inet_pton(socket.AF_INET, ip)
        ip16 = b"\x00" * 10 + b"\xff\xff" + packed
    except OSError:
        ip16 = socket.inet_pton(socket.AF_INET6, ip)
    return struct.pack("<Q", services) + ip16 + struct.pack(">H", port)


def version_payload(peer_ip: str, peer_port: int) -> bytes:
    addr_recv = net_addr(peer_ip, peer_port, services=1)
    addr_from = net_addr("0.0.0.0", 0, services=0)
    return (
        struct.pack("<iQq", PROTOCOL_VERSION, 0, int(time.time()))
        + addr_recv + addr_from
        + struct.pack("<Q", random.getrandbits(64))
        + encode_varstr(b"/ravencrawler:0.2/")
        + struct.pack("<i", 0)
        + b"\x00"
    )


def parse_version_payload(payload: bytes):
    """상대가 보낸 version 메시지에서 subver(클라이언트 버전), start_height를 뽑아냄."""
    try:
        pos = 4 + 8 + 8 + 26 + 26 + 8  # version+services+timestamp+addr_recv+addr_from+nonce
        length, pos = read_varint(payload, pos)
        subver = payload[pos:pos + length].decode("ascii", errors="ignore")
        pos += length
        start_height = struct.unpack("<i", payload[pos:pos + 4])[0] if len(payload) >= pos + 4 else None
        return subver, start_height
    except Exception:
        return None, None


def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("연결 종료됨")
        buf += chunk
    return buf


def read_message(sock: socket.socket):
    header = recv_exact(sock, 24)
    if header[0:4] != MAGIC:
        raise ValueError("잘못된 매직 바이트")
    command = header[4:16].rstrip(b"\x00").decode("ascii", errors="ignore")
    length = struct.unpack("<I", header[16:20])[0]
    payload = recv_exact(sock, length) if length else b""
    return command, payload


def parse_addr_payload(payload: bytes):
    count, pos = read_varint(payload, 0)
    results = []
    for _ in range(count):
        entry = payload[pos:pos + 30]
        if len(entry) < 30:
            break
        pos += 30
        ip_bytes = entry[12:28]
        port = struct.unpack(">H", entry[28:30])[0]
        if ip_bytes[:12] == b"\x00" * 10 + b"\xff\xff":
            ip = socket.inet_ntoa(ip_bytes[12:16])
        else:
            ip = socket.inet_ntop(socket.AF_INET6, ip_bytes)
        results.append((ip, port))
    return results


def handshake(ip: str, port: int, timeout: float):
    sock = socket.create_connection((ip, port), timeout=timeout)
    sock.settimeout(timeout)
    sock.sendall(make_message("version", version_payload(ip, port)))
    got_version = got_verack = False
    subver = None
    height = None
    deadline = time.time() + timeout
    while time.time() < deadline and not (got_version and got_verack):
        cmd, payload = read_message(sock)
        if cmd == "version":
            got_version = True
            subver, height = parse_version_payload(payload)
            sock.sendall(make_message("verack", b""))
        elif cmd == "verack":
            got_verack = True
        elif cmd == "reject":
            raise ConnectionError(f"거부됨(reject): {payload[:60]}")
    if not (got_version and got_verack):
        sock.close()
        raise ConnectionError("핸드셰이크 미완료")
    return sock, subver, height


def request_addrs(sock: socket.socket, wait_seconds: float):
    sock.sendall(make_message("getaddr", b""))
    addrs = []
    deadline = time.time() + wait_seconds
    sock.settimeout(2)
    while time.time() < deadline:
        try:
            cmd, payload = read_message(sock)
        except socket.timeout:
            continue
        except (ConnectionError, OSError, ValueError):
            break
        if cmd == "addr":
            addrs.extend(parse_addr_payload(payload))
        elif cmd == "ping":
            try:
                sock.sendall(make_message("pong", payload))
            except OSError:
                pass
    return addrs


def crawl_peer(ip: str, port: int):
    time.sleep(random.uniform(0, STAGGER_MAX))
    try:
        sock, subver, height = handshake(ip, port, CONNECT_TIMEOUT)
    except Exception:
        return False, [], None, None
    try:
        addrs = request_addrs(sock, ADDR_WAIT)
    except Exception:
        addrs = []
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return True, addrs, subver, height


def resolve_seeds():
    seeds = {(ip, PORT) for ip in KNOWN_GOOD_SEEDS}
    for host in DNS_SEEDS:
        try:
            for info in socket.getaddrinfo(host, PORT, proto=socket.IPPROTO_TCP):
                ip = info[4][0]
                if ":" not in ip:
                    seeds.add((ip, PORT))
        except Exception as e:
            print(f"  ! DNS 시드 조회 실패 ({host}): {e}")
    return seeds


def crawl():
    frontier = resolve_seeds()
    visited = set()
    reachable = {}   # ip -> {"subver":..., "height":...}

    for round_num in range(1, MAX_ROUNDS + 1):
        frontier = {a for a in frontier if a not in visited}
        if not frontier:
            print("더 이상 새로 발견된 주소가 없어 종료합니다.")
            break
        batch = list(frontier)[:NODE_CAP]
        print(f"[라운드 {round_num}] {len(batch)}개 주소에 접속 시도 중...")

        new_addrs = set()
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(crawl_peer, ip, port): (ip, port) for ip, port in batch}
            for fut in as_completed(futures):
                ip, port = futures[fut]
                visited.add((ip, port))
                try:
                    ok, addrs, subver, height = fut.result()
                except Exception:
                    ok, addrs, subver, height = False, [], None, None
                if ok:
                    reachable[ip] = {"subver": subver or "알 수 없음", "height": height}
                    for a in addrs:
                        if a not in visited:
                            new_addrs.add(a)

        print(f"  -> 누적 도달 가능 노드: {len(reachable)}개 / 새로 발견된 주소: {len(new_addrs)}개")
        frontier = new_addrs

    return reachable


# ── GeoIP (ip-api.com, 무료) ──────────────────────────────────────

def geolocate(ips):
    results = {}
    ip_list = list(ips)
    for i in range(0, len(ip_list), 100):
        chunk = ip_list[i:i + 100]
        body = json.dumps(
            [{"query": ip, "fields": "status,country,countryCode,lat,lon,isp,query"} for ip in chunk]
        ).encode("utf-8")
        req = urllib.request.Request(
            "http://ip-api.com/batch", data=body,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for entry in data:
                q = entry.get("query")
                if entry.get("status") == "success":
                    results[q] = {
                        "country": entry.get("country", "알 수 없음"),
                        "countryCode": entry.get("countryCode", ""),
                        "isp": entry.get("isp", "알 수 없음"),
                        "lat": entry.get("lat"),
                        "lon": entry.get("lon"),
                    }
                else:
                    results[q] = {"country": "알 수 없음", "countryCode": "", "isp": "알 수 없음", "lat": None, "lon": None}
        except Exception as e:
            print(f"  ! GeoIP 조회 일부 실패: {e}")
        time.sleep(1.5)
    return results


def load_node_stats():
    if os.path.exists(NODE_STATS_JSON):
        try:
            with open(NODE_STATS_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"run_count": 0, "nodes": {}}


def update_node_stats(reachable_ips, now_iso):
    stats = load_node_stats()
    stats["run_count"] = stats.get("run_count", 0) + 1
    run_count = stats["run_count"]
    nodes = stats.setdefault("nodes", {})

    for ip in reachable_ips:
        entry = nodes.get(ip)
        if entry is None:
            nodes[ip] = {
                "first_seen": now_iso,
                "first_seen_run": run_count,
                "last_seen": now_iso,
                "seen_count": 1,
            }
        else:
            entry["last_seen"] = now_iso
            entry["seen_count"] = entry.get("seen_count", 0) + 1

    # 오랫동안 안 잡힌 노드는 통계 파일에서 정리 (파일 크기 제한)
    now_dt = datetime.now(timezone.utc)
    cutoff = now_dt.timestamp() - NODE_STATS_RETENTION_DAYS * 86400
    for ip in list(nodes.keys()):
        try:
            last_seen_dt = datetime.fromisoformat(nodes[ip]["last_seen"])
            if last_seen_dt.timestamp() < cutoff:
                del nodes[ip]
        except Exception:
            pass

    with open(NODE_STATS_JSON, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


def compute_node_meta(ip, stats, now_dt):
    """개별 노드의 '처음 발견' 라벨과 신뢰도(%)를 계산."""
    entry = stats.get("nodes", {}).get(ip)
    if not entry:
        return {"age_label": "신규 발견", "reachability_pct": 100.0, "seen_count": 1, "checks": 1}

    run_count = stats.get("run_count", 1)
    first_seen_run = entry.get("first_seen_run", run_count)
    checks = max(run_count - first_seen_run + 1, 1)
    seen_count = entry.get("seen_count", 1)
    reachability_pct = round(seen_count / checks * 100, 1)

    try:
        first_seen_dt = datetime.fromisoformat(entry["first_seen"])
        delta = now_dt - first_seen_dt
        if delta.days >= 1:
            age_label = f"{delta.days}일 전 처음 발견"
        elif delta.seconds >= 3600:
            age_label = f"{delta.seconds // 3600}시간 전 처음 발견"
        else:
            age_label = "신규 발견"
    except Exception:
        age_label = "신규 발견"

    return {
        "age_label": age_label,
        "reachability_pct": reachability_pct,
        "seen_count": seen_count,
        "checks": checks,
    }


def top_list(counter: Counter, n=None, code_map=None):
    total = sum(counter.values())
    items = counter.most_common(n) if n else counter.most_common()
    result = []
    for name, cnt in items:
        entry = {"name": name, "count": cnt, "pct": round(cnt / total * 100, 2) if total else 0}
        if code_map is not None:
            entry["code"] = code_map.get(name, "").lower()
        result.append(entry)
    return result


def update_history(total_nodes: int, generated_at: str):
    history = []
    if os.path.exists(HISTORY_JSON):
        try:
            with open(HISTORY_JSON, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
    history.append({"t": generated_at, "total": total_nodes})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    with open(HISTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


SYNC_TOLERANCE_BLOCKS = 50    # 기준 높이 대비 이 블록 수 이내면 "동기화 완료" (크롤링 소요시간 15~20분 동안 쌓이는 자연스러운 오차를 흡수)
STALLED_THRESHOLD_BLOCKS = 500   # 기준 높이보다 이만큼 이상 뒤처지면 "정지된 노드"(사실상 죽은 노드)로 간주. 그 사이는 "지연 중"


def _robust_median(heights):
    """정지된(극단적으로 뒤처진) 노드가 섞여 있어도 기준 높이가 흔들리지 않도록,
    1차 중앙값 근처(±1000블록)로 한 번 걸러낸 뒤 그 안에서 중앙값을 다시 계산."""
    def median_of(values):
        s = sorted(values)
        n = len(s)
        return s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) // 2

    first_pass = median_of(heights)
    filtered = [h for h in heights if abs(h - first_pass) <= 1000]
    if len(filtered) >= max(3, len(heights) * 0.2):
        return median_of(filtered)
    return first_pass   # 필터링 후 표본이 너무 적으면 1차 값을 그대로 사용


MIN_SAMPLE_FOR_REFERENCE = 3   # 기준 버전으로 채택하려면 최소 이 정도 노드 수는 있어야 함 (노이즈/버그성 버전 문자열 방지)


def _parse_subver_version(subver):
    """'/Ravencoin:4.8.0/' 같은 문자열에서 (4,8,0) 형태의 버전 튜플을 뽑아냄. 실패하면 None."""
    if not subver:
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", subver)
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def compute_network_health(reachable):
    """자체 크롤링 결과만으로 (외부 API 의존 없이) 동기화 상태를 3단계로 계산.

    기준 높이는 "가장 인기 많은 버전"이 아니라 "표본이 충분히 있는 것 중 버전 번호가 가장 높은(=최신)
    클라이언트"의 높이로 계산한다. 롤백 이후 방치된 구버전(예: 4.6.x)이 세부 버전 하나에 몰려서
    개수로는 다수가 되더라도, "숫자가 더 큰 최신 버전"이 있다면 그쪽을 기준으로 삼아 착시를 방지한다.
    최신 버전 문자열을 아예 파싱할 수 없는 경우에만, 표본이 가장 많은 버전으로 대체한다.

    - 동기화 완료(synced): 기준 높이 ±50블록 이내 — 정상
    - 지연 중(lagging): 그보다는 뒤처졌지만 아직 500블록 미만 — 막 따라잡는 중일 가능성
    - 정지(stalled): 기준 높이보다 500블록 이상 뒤처짐 — 응답만 하고 사실상 죽은 노드
    """
    version_heights = {}
    for v in reachable.values():
        h = v.get("height")
        if isinstance(h, int) and h > 0:
            version_heights.setdefault(v.get("subver") or "알 수 없음", []).append(h)

    if not version_heights:
        return {"reference_height": None, "reference_version": None, "synced": 0, "lagging": 0, "stalled": 0, "unknown": len(reachable), "stalled_versions": []}

    # 1순위: 표본이 충분한 버전들 중 버전 번호가 가장 높은 것
    parsable = [
        (ver, heights, _parse_subver_version(ver))
        for ver, heights in version_heights.items()
        if len(heights) >= MIN_SAMPLE_FOR_REFERENCE and _parse_subver_version(ver) is not None
    ]
    if parsable:
        reference_version, dominant_heights, _ = max(parsable, key=lambda item: item[2])
    else:
        # 2순위(대체): 버전 파싱이 다 실패하면 표본이 가장 많은 버전으로
        reference_version, dominant_heights = max(version_heights.items(), key=lambda kv: len(kv[1]))

    median = _robust_median(dominant_heights)

    synced = lagging = stalled = 0
    stalled_version_counter = Counter()
    for v in reachable.values():
        h = v.get("height")
        if not isinstance(h, int) or h <= 0:
            continue
        behind = median - h   # 양수면 기준 높이보다 뒤처진 것
        if abs(h - median) <= SYNC_TOLERANCE_BLOCKS:
            synced += 1
        elif behind >= STALLED_THRESHOLD_BLOCKS:
            stalled += 1
            stalled_version_counter[v.get("subver") or "알 수 없음"] += 1
        else:
            lagging += 1
    unknown = len(reachable) - synced - lagging - stalled

    return {
        "reference_height": median,
        "reference_version": reference_version,
        "synced": synced,
        "lagging": lagging,
        "stalled": stalled,
        "unknown": unknown,
        "stalled_versions": top_list(stalled_version_counter, None) if stalled else [],
    }


def main():
    print("Ravencoin 네트워크 크롤링 시작...")
    reachable = crawl()  # ip -> {"subver":..., "height":...}
    print(f"총 도달 가능 노드: {len(reachable)}개")

    geo = geolocate(reachable.keys()) if reachable else {}
    health = compute_network_health(reachable)
    print(f"네트워크 상태: 기준 높이={health['reference_height']} 동기화={health['synced']} 지연={health['lagging']} 정지={health['stalled']} 알수없음={health['unknown']}")

    country_counter = Counter()
    isp_counter = Counter()
    version_counter = Counter()
    country_code_map = {}   # 국가명 -> ISO 코드 (국기 표시용)
    for ip, node_info in reachable.items():
        info = geo.get(ip, {"country": "알 수 없음", "countryCode": "", "isp": "알 수 없음"})
        country_counter[info["country"]] += 1
        isp_counter[info["isp"]] += 1
        version_counter[node_info["subver"]] += 1
        if info["country"] not in country_code_map:
            country_code_map[info["country"]] = info.get("countryCode", "")

    generated_at = datetime.now(timezone.utc).isoformat()
    node_stats = update_node_stats(reachable.keys(), generated_at)
    now_dt = datetime.now(timezone.utc)

    ref_height = health["reference_height"]
    node_list = []
    for ip, node_info in sorted(reachable.items()):
        info = geo.get(ip, {"country": "알 수 없음", "countryCode": "", "isp": "알 수 없음", "lat": None, "lon": None})
        meta = compute_node_meta(ip, node_stats, now_dt)
        height = node_info.get("height")
        sync_status = "unknown"
        if isinstance(height, int) and height > 0 and ref_height is not None:
            behind = ref_height - height
            if abs(height - ref_height) <= SYNC_TOLERANCE_BLOCKS:
                sync_status = "synced"
            elif behind >= STALLED_THRESHOLD_BLOCKS:
                sync_status = "stalled"
            else:
                sync_status = "lagging"
        node_list.append({
            "ip": ip,
            "port": PORT,
            "country": info["country"],
            "country_code": info.get("countryCode", "").lower(),
            "isp": info["isp"],
            "version": node_info["subver"],
            "height": height,
            "sync_status": sync_status,
            "lat": info.get("lat"),
            "lon": info.get("lon"),
            "age_label": meta["age_label"],
            "reachability_pct": meta["reachability_pct"],
            "checks": meta["checks"],
        })

    result = {
        "generated_at": generated_at,
        "total_nodes": len(reachable),   # 전체 도달 가능 노드 수 (기존 지표, 변경 없음)
        "network_health": health,        # 부가 지표: 동기화 상태 (신규)
        "countries": top_list(country_counter, None, code_map=country_code_map),   # 전체 국가 (1개짜리도 포함)
        "isps": top_list(isp_counter, 15),
        "versions": top_list(version_counter, 15),
        "nodes": node_list,   # 개별 노드 검색용 (IP로 내 노드가 잡혔는지 확인 가능)
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    update_history(result["total_nodes"], result["generated_at"])

    print(f"결과를 {OUTPUT_JSON} 에 저장했습니다.")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
