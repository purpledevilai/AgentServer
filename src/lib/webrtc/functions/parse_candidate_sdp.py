def parse_candidate_sdp(candidate_sdp: str) -> dict:
    parts = candidate_sdp.split()

    if parts[0].startswith("candidate:"):
        foundation = parts[0].split(":")[1]
    else:
        raise ValueError("Invalid candidate string")

    component = int(parts[1])
    transport = parts[2].lower()  # "udp" or "tcp"
    priority = int(parts[3])
    ip = parts[4]
    port = int(parts[5])
    candidate_type = parts[7]  # 'typ' is at index 6, type is 7

    return {
        "foundation": foundation,
        "component": component,
        "protocol": transport,
        "priority": priority,
        "ip": ip,
        "port": port,
        "type": candidate_type
    }