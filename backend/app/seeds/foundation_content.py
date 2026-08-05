"""Authored content for the Foundations track.

Plain data — no database imports — so it can be validated, diffed and reviewed
like the editorial artefact it is. `app.seeds.runner` turns it into rows.

Technical accuracy is the point here: these lessons teach CCNA material, and a
wrong host count or a mislabelled OSI layer is a defect, not a typo.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------- #
# Track
# --------------------------------------------------------------------------- #
FOUNDATION_TRACK: dict[str, Any] = {
    "slug": "foundations",
    "title": "Foundations",
    "description": (
        "How networks actually move data — the OSI and TCP/IP models, "
        "addressing, subnetting, switching and routing. Everything the later "
        "tracks assume you already know."
    ),
    "level": "foundation",
    "icon": "layers",
    "accent_color": "var(--color-track-foundation)",
    "order_index": 0,
    "is_published": True,
}


# --------------------------------------------------------------------------- #
# Course 1 — Network Fundamentals
# --------------------------------------------------------------------------- #
OSI_LESSON: dict[str, Any] = {
    "slug": "osi-model",
    "title": "The OSI Model",
    "summary": "Seven layers, what each one is responsible for, and why the model is worth learning.",
    "lesson_type": "theory",
    "estimated_minutes": 15,
    "xp_reward": 20,
    "objectives": [
        "Name the seven OSI layers in order",
        "State the responsibility of each layer",
        "Match a protocol or device to the layer it operates at",
        "Explain what encapsulation does as data moves down the stack",
    ],
    "content_blocks": [
        {
            "type": "paragraph",
            "text": (
                "The Open Systems Interconnection model splits networking into seven "
                "layers, each with one job. No production network is literally built "
                "in seven layers — but the model gives you a shared vocabulary and, "
                "more usefully, a troubleshooting order."
            ),
        },
        {
            "type": "callout",
            "variant": "tip",
            "title": "Why this matters in practice",
            "text": (
                "When a user says 'the network is down', the layers tell you where to "
                "start. Is the interface up (Layer 1)? Do you have a MAC address "
                "(Layer 2)? Can you ping the gateway (Layer 3)? Working bottom-up "
                "stops you debugging DNS when a cable is unplugged."
            ),
        },
        {"type": "heading", "level": 2, "text": "The seven layers"},
        {
            "type": "interactive",
            "widget": "osi-stack",
            "title": "Explore the stack",
        },
        {
            "type": "table",
            "caption": "The OSI layers, top to bottom.",
            "headers": ["#", "Layer", "Responsibility", "Examples"],
            "rows": [
                ["7", "Application", "Interface to the user's application", "HTTP, DNS, SMTP"],
                ["6", "Presentation", "Encoding, encryption, compression", "TLS, JPEG, ASCII"],
                ["5", "Session", "Establishing and ending conversations", "RPC, NetBIOS"],
                ["4", "Transport", "End-to-end delivery, ports, reliability", "TCP, UDP"],
                ["3", "Network", "Logical addressing and path selection", "IP, ICMP, OSPF"],
                ["2", "Data Link", "Framing and local delivery on one link", "Ethernet, ARP, PPP"],
                ["1", "Physical", "Bits on the wire, voltages, connectors", "Cables, RJ45, fibre"],
            ],
        },
        {
            "type": "callout",
            "variant": "exam",
            "title": "Remembering the order",
            "text": (
                "Bottom-up: Please Do Not Throw Sausage Pizza Away — Physical, Data "
                "Link, Network, Transport, Session, Presentation, Application. Know it "
                "in both directions; exam questions ask either way."
            ),
        },
        {"type": "heading", "level": 2, "text": "Encapsulation"},
        {
            "type": "paragraph",
            "text": (
                "As data moves down the stack, each layer wraps it in its own header. "
                "The receiving host reverses the process on the way up. The unit of "
                "data has a different name at each layer, and interviewers ask for "
                "these by name."
            ),
        },
        {
            "type": "definitions",
            "items": [
                {
                    "term": "Data (Layers 5-7)",
                    "definition": "The payload as the application produced it.",
                },
                {
                    "term": "Segment (Layer 4)",
                    "definition": "Payload plus a TCP header. With UDP the unit is called a datagram.",
                },
                {
                    "term": "Packet (Layer 3)",
                    "definition": "Segment plus an IP header carrying source and destination IP addresses.",
                },
                {
                    "term": "Frame (Layer 2)",
                    "definition": "Packet plus an Ethernet header with source and destination MAC addresses, and a trailing checksum.",
                },
                {
                    "term": "Bits (Layer 1)",
                    "definition": "The frame encoded as electrical, optical or radio signals.",
                },
            ],
        },
        {
            "type": "callout",
            "variant": "important",
            "title": "The addresses change, the packet does not",
            "text": (
                "IP addresses stay the same end to end. MAC addresses are rewritten at "
                "every hop, because they only identify devices on one link. This single "
                "idea explains most of routing."
            ),
        },
        {"type": "heading", "level": 2, "text": "Which layer is that device?"},
        {
            "type": "table",
            "headers": ["Device", "Layer", "Decision it makes"],
            "rows": [
                ["Hub", "1", "None — repeats bits out of every port"],
                ["Switch", "2", "Forwards frames by destination MAC address"],
                ["Router", "3", "Forwards packets by destination IP network"],
                ["Firewall", "3-7", "Permits or denies by address, port, or application"],
            ],
        },
    ],
}

TCPIP_LESSON: dict[str, Any] = {
    "slug": "tcp-ip-model",
    "title": "The TCP/IP Model",
    "summary": "The four-layer model networks are actually built on, and how it maps to OSI.",
    "lesson_type": "theory",
    "estimated_minutes": 12,
    "xp_reward": 20,
    "objectives": [
        "Name the four TCP/IP layers",
        "Map TCP/IP layers onto the OSI model",
        "Contrast TCP with UDP and choose between them",
    ],
    "content_blocks": [
        {
            "type": "paragraph",
            "text": (
                "OSI is the teaching model. TCP/IP is the one the internet actually "
                "runs on. It collapses OSI's seven layers into four, mostly by merging "
                "the top three."
            ),
        },
        {
            "type": "table",
            "caption": "TCP/IP mapped onto OSI.",
            "headers": ["TCP/IP layer", "OSI equivalent", "Protocols"],
            "rows": [
                ["Application", "5, 6, 7", "HTTP, DNS, DHCP, SMTP, SSH"],
                ["Transport", "4", "TCP, UDP"],
                ["Internet", "3", "IP, ICMP, ARP"],
                ["Network Access", "1, 2", "Ethernet, Wi-Fi, fibre"],
            ],
        },
        {"type": "heading", "level": 2, "text": "TCP or UDP?"},
        {
            "type": "paragraph",
            "text": (
                "Both are Layer 4. The choice is between guaranteed delivery and low "
                "latency — you cannot have both, and the application decides which "
                "matters."
            ),
        },
        {
            "type": "table",
            "headers": ["", "TCP", "UDP"],
            "rows": [
                ["Connection", "Connection-oriented", "Connectionless"],
                ["Reliability", "Retransmits lost data", "No retransmission"],
                ["Ordering", "Reassembles in order", "No ordering guarantee"],
                ["Header size", "20 bytes minimum", "8 bytes"],
                ["Typical use", "Web, email, file transfer", "Voice, video, DNS queries"],
            ],
        },
        {
            "type": "callout",
            "variant": "tip",
            "title": "Why voice uses UDP",
            "text": (
                "In a call, a retransmitted packet arrives too late to play. "
                "Retransmission would add delay to fix audio nobody can use — so voice "
                "accepts loss and keeps latency low."
            ),
        },
        {"type": "heading", "level": 2, "text": "The TCP three-way handshake"},
        {
            "type": "interactive",
            "widget": "tcp-handshake",
            "title": "Watch the handshake",
        },
        {
            "type": "list",
            "ordered": True,
            "items": [
                "SYN — the client proposes a connection and its starting sequence number.",
                "SYN-ACK — the server acknowledges and sends its own sequence number.",
                "ACK — the client acknowledges the server's number. Data can now flow.",
            ],
        },
        {
            "type": "callout",
            "variant": "exam",
            "text": (
                "Closing a TCP connection normally takes four messages "
                "(FIN, ACK, FIN, ACK), not three. Opening is three, closing is four."
            ),
        },
    ],
}

OSI_QUIZ: dict[str, Any] = {
    "title": "Check: models and encapsulation",
    "instructions": "Six questions on the OSI and TCP/IP models. You need 70% to pass.",
    "passing_score": 70,
    "questions": [
        {
            "prompt": "Which OSI layer is responsible for logical addressing and path selection?",
            "question_type": "single_choice",
            "points": 1,
            "explanation": (
                "Layer 3, the Network layer, carries IP addresses and makes routing "
                "decisions. Layer 2 handles delivery within a single link."
            ),
            "options": [
                {"text": "Layer 2 — Data Link", "is_correct": False},
                {"text": "Layer 3 — Network", "is_correct": True},
                {"text": "Layer 4 — Transport", "is_correct": False},
                {"text": "Layer 7 — Application", "is_correct": False},
            ],
        },
        {
            "prompt": "A switch forwards traffic based on MAC addresses. At which layer does it operate?",
            "question_type": "single_choice",
            "points": 1,
            "explanation": "MAC addresses live in the Ethernet frame header, which is Layer 2.",
            "options": [
                {"text": "Layer 1", "is_correct": False},
                {"text": "Layer 2", "is_correct": True},
                {"text": "Layer 3", "is_correct": False},
                {"text": "Layer 4", "is_correct": False},
            ],
        },
        {
            "prompt": "Select every statement that is true of UDP.",
            "question_type": "multiple_choice",
            "points": 2,
            "explanation": (
                "UDP is connectionless with an 8-byte header and no retransmission. "
                "Guaranteed delivery and ordering are TCP features."
            ),
            "options": [
                {"text": "It is connectionless", "is_correct": True},
                {"text": "Its header is 8 bytes", "is_correct": True},
                {"text": "It retransmits lost segments", "is_correct": False},
                {"text": "It guarantees ordered delivery", "is_correct": False},
            ],
        },
        {
            "prompt": "TCP is connection-oriented and guarantees delivery.",
            "question_type": "true_false",
            "points": 1,
            "explanation": "TCP establishes a connection and retransmits anything unacknowledged.",
            "options": [
                {"text": "True", "is_correct": True},
                {"text": "False", "is_correct": False},
            ],
        },
        {
            "prompt": "What is the Layer 3 protocol data unit called?",
            "question_type": "fill_blank",
            "points": 1,
            "explanation": "Layer 3 produces a packet. Layer 4 makes segments, Layer 2 makes frames.",
            "answer_key": {"text": "packet", "accepted": ["packet", "a packet", "ip packet"]},
        },
        {
            "prompt": "Put the TCP three-way handshake in order, first message first.",
            "question_type": "ordering",
            "points": 2,
            "explanation": "The client sends SYN, the server replies SYN-ACK, the client sends ACK.",
            "options": [
                {"text": "SYN", "is_correct": False},
                {"text": "SYN-ACK", "is_correct": False},
                {"text": "ACK", "is_correct": False},
            ],
            # Ordering answers are compared against option *text*.
            "answer_key": {"order": ["SYN", "SYN-ACK", "ACK"]},
        },
    ],
}

FUNDAMENTALS_COURSE: dict[str, Any] = {
    "slug": "network-fundamentals",
    "title": "Network Fundamentals",
    "summary": "The models everything else is built on: OSI, TCP/IP, and encapsulation.",
    "description": (
        "Start here. This course covers the two layered models used to describe "
        "networks, how data is wrapped as it travels down the stack, and how to "
        "use the layers as a troubleshooting order."
    ),
    "difficulty": "beginner",
    "estimated_minutes": 30,
    "tags": ["ccna", "osi", "tcp-ip", "fundamentals"],
    "prerequisites": [],
    "order_index": 0,
    "is_published": True,
    "grants_certificate": False,
    "modules": [
        {
            "slug": "layered-models",
            "title": "Layered models",
            "description": "How networking is broken into layers, and why.",
            "order_index": 0,
            "lessons": [
                {**OSI_LESSON, "order_index": 0, "quiz": OSI_QUIZ},
                {**TCPIP_LESSON, "order_index": 1},
            ],
        }
    ],
}


# --------------------------------------------------------------------------- #
# Course 2 — IPv4 Addressing and Subnetting
# --------------------------------------------------------------------------- #
IPV4_LESSON: dict[str, Any] = {
    "slug": "ipv4-addressing",
    "title": "IPv4 Addressing",
    "summary": "32 bits, dotted decimal, the network/host split, and the private ranges.",
    "lesson_type": "theory",
    "estimated_minutes": 15,
    "xp_reward": 20,
    "objectives": [
        "Convert between dotted decimal and binary",
        "Identify the network and host portions of an address",
        "Recognise the RFC 1918 private ranges",
        "Explain what a subnet mask does",
    ],
    "content_blocks": [
        {
            "type": "paragraph",
            "text": (
                "An IPv4 address is 32 bits. We write it as four decimal numbers "
                "separated by dots — each number is one byte, so each ranges from 0 "
                "to 255."
            ),
        },
        {"type": "interactive", "widget": "ipv4-anatomy", "title": "Anatomy of an address"},
        {
            "type": "callout",
            "variant": "note",
            "title": "Why 255 is the maximum",
            "text": (
                "Eight bits all set to 1 is 128+64+32+16+8+4+2+1 = 255. That is why "
                "no octet ever exceeds it — 300.1.1.1 is not a typo, it is impossible."
            ),
        },
        {"type": "heading", "level": 2, "text": "The mask splits the address"},
        {
            "type": "paragraph",
            "text": (
                "An address alone does not tell you which network it belongs to. The "
                "subnet mask does: every bit set to 1 marks a network bit, every 0 "
                "marks a host bit. The 1s are always contiguous and always on the left."
            ),
        },
        {
            "type": "table",
            "caption": "Common masks in both notations.",
            "headers": ["Prefix", "Dotted decimal", "Network bits", "Usable hosts"],
            "rows": [
                ["/8", "255.0.0.0", "8", "16,777,214"],
                ["/16", "255.255.0.0", "16", "65,534"],
                ["/24", "255.255.255.0", "24", "254"],
                ["/25", "255.255.255.128", "25", "126"],
                ["/26", "255.255.255.192", "26", "62"],
                ["/30", "255.255.255.252", "30", "2"],
            ],
        },
        {
            "type": "callout",
            "variant": "important",
            "title": "Why 'minus two'",
            "text": (
                "Usable hosts are 2^h - 2, where h is the number of host bits. The two "
                "excluded addresses are the network address (all host bits 0) and the "
                "broadcast address (all host bits 1). Neither can be assigned to a "
                "device. A /30 gives 2^2 - 2 = 2 usable addresses, which is exactly "
                "what a point-to-point link between two routers needs."
            ),
        },
        {"type": "heading", "level": 2, "text": "Private address ranges"},
        {
            "type": "paragraph",
            "text": (
                "RFC 1918 reserves three ranges that are not routable on the public "
                "internet. Every home and office network uses one of them, and NAT "
                "translates them to a public address on the way out."
            ),
        },
        {
            "type": "table",
            "headers": ["Range", "Prefix", "Addresses", "Typically used by"],
            "rows": [
                ["10.0.0.0 - 10.255.255.255", "10.0.0.0/8", "16.7 million", "Large enterprises"],
                ["172.16.0.0 - 172.31.255.255", "172.16.0.0/12", "1 million", "Medium networks"],
                [
                    "192.168.0.0 - 192.168.255.255",
                    "192.168.0.0/16",
                    "65,536",
                    "Home and small office",
                ],
            ],
        },
        {
            "type": "callout",
            "variant": "exam",
            "text": (
                "The 172.16.0.0/12 range ends at 172.31.255.255, not 172.16.255.255. "
                "A /12 covers 16 second octets: 16 through 31. This is a favourite "
                "exam trap."
            ),
        },
        {"type": "heading", "level": 2, "text": "Addresses you cannot assign"},
        {
            "type": "definitions",
            "items": [
                {
                    "term": "Network address",
                    "definition": "All host bits 0 — names the network itself, e.g. 192.168.1.0/24.",
                },
                {
                    "term": "Broadcast address",
                    "definition": "All host bits 1 — reaches every host on the network, e.g. 192.168.1.255/24.",
                },
                {"term": "127.0.0.0/8", "definition": "Loopback. 127.0.0.1 is always this host."},
                {
                    "term": "169.254.0.0/16",
                    "definition": "APIPA — self-assigned when DHCP fails. Seeing one is a symptom, not a configuration.",
                },
            ],
        },
        {
            "type": "callout",
            "variant": "tip",
            "title": "Troubleshooting shortcut",
            "text": (
                "A host with a 169.254.x.x address did not get a reply from a DHCP "
                "server. Check the cable, the VLAN, and whether the DHCP scope has "
                "run out — not the host's IP settings."
            ),
        },
    ],
}

SUBNETTING_LESSON: dict[str, Any] = {
    "slug": "subnetting",
    "title": "Subnetting",
    "summary": "Splitting a network into smaller ones, and doing it quickly under exam pressure.",
    "lesson_type": "interactive",
    "estimated_minutes": 25,
    "xp_reward": 30,
    "objectives": [
        "Explain why networks are subnetted",
        "Calculate subnet, broadcast and host ranges from an address and mask",
        "Use the magic-number method to subnet quickly",
        "Choose a mask that fits a required host count",
    ],
    "content_blocks": [
        {
            "type": "paragraph",
            "text": (
                "Subnetting borrows bits from the host portion and gives them to the "
                "network portion. You get more networks, each with fewer hosts."
            ),
        },
        {
            "type": "callout",
            "variant": "tip",
            "title": "Why bother",
            "text": (
                "Broadcast containment, security boundaries, and address efficiency. "
                "A single flat /16 with 40,000 hosts would drown in broadcast traffic "
                "and give you no place to apply policy."
            ),
        },
        {"type": "heading", "level": 2, "text": "The magic-number method"},
        {
            "type": "paragraph",
            "text": (
                "This is the fastest reliable way to subnet by hand. Work in the "
                "octet where the mask stops being 255 — the 'interesting octet'."
            ),
        },
        {
            "type": "list",
            "ordered": True,
            "items": [
                "Find the interesting octet — the one where the mask is neither 255 nor 0.",
                "Magic number = 256 minus the mask value in that octet.",
                "Subnets start at multiples of the magic number: 0, magic, 2x magic...",
                "The broadcast address is one below the next subnet's start.",
                "Usable hosts are everything between the network and broadcast addresses.",
            ],
        },
        {
            "type": "callout",
            "variant": "note",
            "title": "Worked example: 192.168.1.100/26",
            "text": (
                "A /26 is 255.255.255.192, so the interesting octet is the fourth and "
                "the magic number is 256 - 192 = 64. Subnets begin at 0, 64, 128 and "
                "192. The address .100 falls in the 64 block. Network 192.168.1.64, "
                "broadcast 192.168.1.127, usable range .65 to .126 — that is 62 hosts."
            ),
        },
        {"type": "interactive", "widget": "subnet-calculator", "title": "Try it yourself"},
        {"type": "heading", "level": 2, "text": "Sizing a subnet"},
        {
            "type": "paragraph",
            "text": (
                "Going the other way — you are told how many hosts are needed and must "
                "pick a mask. Find the smallest number of host bits h where 2^h - 2 "
                "covers the requirement."
            ),
        },
        {
            "type": "table",
            "headers": ["Hosts needed", "Host bits", "Usable", "Prefix"],
            "rows": [
                ["2", "2", "2", "/30"],
                ["10", "4", "14", "/28"],
                ["25", "5", "30", "/27"],
                ["50", "6", "62", "/26"],
                ["100", "7", "126", "/25"],
                ["200", "8", "254", "/24"],
            ],
        },
        {
            "type": "callout",
            "variant": "exam",
            "title": "Always round up",
            "text": (
                "Needing 30 hosts does not fit a /27, which gives exactly 30 usable — "
                "it fits, but leaves no room for the gateway. Count the router "
                "interface as a host: 30 PCs plus a gateway needs 31, so use a /26."
            ),
        },
        {"type": "heading", "level": 2, "text": "Configuring it on a router"},
        {
            "type": "code",
            "language": "cisco",
            "caption": "Assigning the gateway address for the 192.168.1.64/26 subnet.",
            "code": (
                "Router> enable\n"
                "Router# configure terminal\n"
                "Router(config)# interface GigabitEthernet0/0\n"
                "Router(config-if)# ip address 192.168.1.65 255.255.255.192\n"
                "Router(config-if)# no shutdown\n"
                "Router(config-if)# end\n"
                "Router# show ip interface brief"
            ),
        },
        {
            "type": "callout",
            "variant": "warning",
            "title": "no shutdown",
            "text": (
                "Router interfaces are administratively down by default. Configure the "
                "address, then bring the interface up — forgetting 'no shutdown' is the "
                "single most common reason a correctly addressed link does not work."
            ),
        },
    ],
}

SUBNETTING_QUIZ: dict[str, Any] = {
    "title": "Check: addressing and subnetting",
    "instructions": "Six questions. Work them out on paper before answering — you need 70%.",
    "passing_score": 70,
    "questions": [
        {
            "prompt": "How many usable host addresses does a /26 subnet provide?",
            "question_type": "single_choice",
            "points": 1,
            "explanation": "A /26 leaves 6 host bits: 2^6 - 2 = 62 usable addresses.",
            "options": [
                {"text": "30", "is_correct": False},
                {"text": "62", "is_correct": True},
                {"text": "64", "is_correct": False},
                {"text": "126", "is_correct": False},
            ],
        },
        {
            "prompt": "What is the network address for the host 192.168.1.100/26?",
            "question_type": "subnet_calc",
            "points": 2,
            "explanation": (
                "The magic number is 256 - 192 = 64, so subnets start at 0, 64, 128, "
                "192. The address .100 falls in the 64 block, making the network "
                "192.168.1.64."
            ),
            "answer_key": {
                "text": "192.168.1.64",
                "accepted": ["192.168.1.64", "192.168.1.64/26"],
            },
        },
        {
            "prompt": "What is the broadcast address of 10.1.1.0/24?",
            "question_type": "subnet_calc",
            "points": 1,
            "explanation": "With all 8 host bits set to 1, the broadcast address is 10.1.1.255.",
            "answer_key": {"text": "10.1.1.255", "accepted": ["10.1.1.255"]},
        },
        {
            "prompt": "Select every range reserved for private use by RFC 1918.",
            "question_type": "multiple_choice",
            "points": 2,
            "explanation": (
                "The three private ranges are 10.0.0.0/8, 172.16.0.0/12 and "
                "192.168.0.0/16. 169.254.0.0/16 is APIPA — reserved, but for "
                "link-local self-assignment, not private addressing."
            ),
            "options": [
                {"text": "10.0.0.0/8", "is_correct": True},
                {"text": "172.16.0.0/12", "is_correct": True},
                {"text": "192.168.0.0/16", "is_correct": True},
                {"text": "169.254.0.0/16", "is_correct": False},
            ],
        },
        {
            "prompt": "Which mask should you use for a point-to-point link between two routers?",
            "question_type": "single_choice",
            "points": 1,
            "explanation": (
                "A /30 gives exactly 2 usable addresses — one per router — and wastes nothing."
            ),
            "options": [
                {"text": "/24", "is_correct": False},
                {"text": "/28", "is_correct": False},
                {"text": "/30", "is_correct": True},
                {"text": "/32", "is_correct": False},
            ],
        },
        {
            "prompt": (
                "Which command assigns 192.168.1.65/26 to an interface? "
                "Type the full command as you would in interface configuration mode."
            ),
            "question_type": "cli_command",
            "points": 2,
            "explanation": (
                "IOS takes the mask in dotted decimal on this command, not as a "
                "prefix length: ip address 192.168.1.65 255.255.255.192"
            ),
            "answer_key": {
                "text": "ip address 192.168.1.65 255.255.255.192",
                "accepted": [
                    "ip address 192.168.1.65 255.255.255.192",
                    "ip addr 192.168.1.65 255.255.255.192",
                ],
            },
        },
    ],
}

SUBNETTING_COURSE: dict[str, Any] = {
    "slug": "ipv4-addressing-subnetting",
    "title": "IPv4 Addressing & Subnetting",
    "summary": "Read an address, split a network, and size a subnet without a calculator.",
    "description": (
        "Subnetting is the skill CCNA candidates most often fail on, purely "
        "because it needs speed as well as understanding. This course builds "
        "both, finishing with the magic-number method you can run in your head."
    ),
    "difficulty": "beginner",
    "estimated_minutes": 40,
    "tags": ["ccna", "ipv4", "subnetting", "addressing"],
    "prerequisites": ["network-fundamentals"],
    "order_index": 1,
    "is_published": True,
    "grants_certificate": True,
    "modules": [
        {
            "slug": "addressing",
            "title": "Addressing and subnetting",
            "description": "From dotted decimal to VLSM.",
            "order_index": 0,
            "lessons": [
                {**IPV4_LESSON, "order_index": 0},
                {**SUBNETTING_LESSON, "order_index": 1, "quiz": SUBNETTING_QUIZ},
            ],
        }
    ],
}


FOUNDATION_COURSES: list[dict[str, Any]] = [FUNDAMENTALS_COURSE, SUBNETTING_COURSE]

# Defined but unpublished, so the catalogue shows the shape of the roadmap
# without pretending the content exists.
PLACEHOLDER_TRACKS: list[dict[str, Any]] = [
    {
        "slug": "intermediate",
        "title": "Intermediate",
        "description": (
            "VLANs, STP, EtherChannel, ACLs, static and dynamic routing with OSPF "
            "and EIGRP, IPv6, wireless, QoS and network security."
        ),
        "level": "intermediate",
        "icon": "network",
        "accent_color": "var(--color-track-intermediate)",
        "order_index": 1,
        "is_published": False,
    },
    {
        "slug": "advanced",
        "title": "Advanced",
        "description": (
            "Enterprise design, data centres, SDN, cloud and Azure networking, "
            "automation with Python, high availability and monitoring."
        ),
        "level": "advanced",
        "icon": "graduation-cap",
        "accent_color": "var(--color-track-advanced)",
        "order_index": 2,
        "is_published": False,
    },
]
