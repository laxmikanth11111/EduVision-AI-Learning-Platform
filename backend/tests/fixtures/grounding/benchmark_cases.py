"""Grounding benchmark cases for precision / recall evaluation.

Each case is a (source, claim, expected_deterministic, expected_llm, risk, category, description) tuple.
The deterministic expectation is what the DeterministicGroundingVerifier
genuinely returns on the given (source, claim) pair.  The LLM expectation is
what a competent entailment model would return — it defines the *reference*
standard, not the test outcome.

Categories:
  restatement       – verbatim or near-verbatim rephrasing of source
  paraphrase        – semantically faithful but different words (deterministic: UNCERTAIN, llm: SUPPORTED)
  unsupported       – added absolute/universal claim not in source
  contradiction     – reversed predicate or antonym
  vocab_overlap     – shared vocabulary but swapped fact (deterministic: UNCERTAIN, llm: UNSUPPORTED)
  numeric_causal    – fabricated numeric or causal detail
  educational_injection – legitimate content discussing injection (must pass both)
"""

from __future__ import annotations

from typing import Literal

GroundingVerdictString = Literal["supported", "unsupported", "contradicted", "uncertain"]
Risk = Literal["high", "low"]


class BenchmarkCase:
    __slots__ = (
        "source",
        "claim",
        "expected_deterministic",
        "expected_llm",
        "risk",
        "category",
        "description",
        "deterministic_known_limitation",
    )

    def __init__(
        self,
        *,
        source: str,
        claim: str,
        expected_deterministic: GroundingVerdictString,
        expected_llm: GroundingVerdictString,
        risk: Risk,
        category: str,
        description: str,
        deterministic_known_limitation: bool = False,
    ) -> None:
        self.source = source
        self.claim = claim
        self.expected_deterministic = expected_deterministic
        self.expected_llm = expected_llm
        self.risk = risk
        self.category = category
        self.description = description
        self.deterministic_known_limitation = deterministic_known_limitation


# ─────────────────────────────────────────────────────────────────────────────
# SUPPORTED / RESTATED (exact or near-verbatim rephrasing)
# ─────────────────────────────────────────────────────────────────────────────

RESTATED = [
    BenchmarkCase(
        source="TCP uses a three-way handshake to establish a connection.",
        claim="TCP uses a three-way handshake to establish a connection.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Exact verbatim",
    ),
    BenchmarkCase(
        source="HTTP is stateless and does not store session data.",
        claim="HTTP is stateless.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Single sentence restated (2-token claim, containment 1.0)",
    ),
    BenchmarkCase(
        source="DNS resolves domain names into IP addresses.",
        claim="DNS resolves domain names into IP addresses.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim DNS",
    ),
    BenchmarkCase(
        source="SSH encrypts all traffic between client and server.",
        claim="SSH encrypts all traffic between client and server.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim SSH",
    ),
    BenchmarkCase(
        source="The OSI model has seven layers.",
        claim="The OSI model has seven layers.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Exact numeric restatement",
    ),
    BenchmarkCase(
        source="TCP uses a three-way handshake. HTTP is stateless.",
        claim="HTTP is stateless.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Second sentence extracted (2-token claim, containment 1.0)",
    ),
    BenchmarkCase(
        source="BGP is used to exchange routing information between autonomous systems.",
        claim="BGP is used to exchange routing information between autonomous systems.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim BGP",
    ),
    BenchmarkCase(
        source="Ethernet operates at layer two of the OSI model.",
        claim="Ethernet operates at layer two of the OSI model.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim Ethernet",
    ),
    BenchmarkCase(
        source="TCP retransmits lost packets to ensure reliable delivery.",
        claim="TCP retransmits lost packets to ensure reliable delivery.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim TCP reliability",
    ),
    BenchmarkCase(
        source="FTP uses two separate channels for control and data.",
        claim="FTP uses two separate channels for control and data.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim FTP",
    ),
    BenchmarkCase(
        source="ARP maps IP addresses to MAC addresses on a local network.",
        claim="ARP maps IP addresses to MAC addresses on a local network.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim ARP",
    ),
    BenchmarkCase(
        source="TLS provides encryption and authentication for web traffic.",
        claim="TLS provides encryption and authentication for web traffic.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim TLS",
    ),
    BenchmarkCase(
        source="ICMP is used to send error messages and operational information.",
        claim="ICMP is used to send error messages and operational information.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim ICMP",
    ),
    BenchmarkCase(
        source="UDP does not guarantee packet delivery order.",
        claim="UDP does not guarantee packet delivery order.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim UDP",
    ),
    BenchmarkCase(
        source="DHCP automatically assigns IP addresses to devices on a network.",
        claim="DHCP automatically assigns IP addresses to devices on a network.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim DHCP",
    ),
    BenchmarkCase(
        source="NAT translates private IP addresses to public IP addresses.",
        claim="NAT translates private IP addresses to public IP addresses.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim NAT",
    ),
    BenchmarkCase(
        source="OSPF is a link-state routing protocol.",
        claim="OSPF is a link-state routing protocol.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim OSPF",
    ),
    BenchmarkCase(
        source="VLANs logically segment a physical network into separate broadcast domains.",
        claim="VLANs logically segment a physical network into separate broadcast domains.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim VLAN",
    ),
    BenchmarkCase(
        source="GRE encapsulates a wide variety of network layer protocols inside virtual point-to-point tunnels.",
        claim="GRE encapsulates a wide variety of network layer protocols inside virtual point-to-point tunnels.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim GRE",
    ),
    BenchmarkCase(
        source="TTL prevents packets from circulating indefinitely in a network.",
        claim="TTL prevents packets from circulating indefinitely in a network.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim TTL",
    ),
    BenchmarkCase(
        source="802.11ac operates only in the 5 GHz frequency band.",
        claim="802.11ac operates only in the 5 GHz frequency band.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="restatement",
        description="Verbatim 802.11ac",
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# PARAPHRASE (semantically faithful, different words)
# Deterministic: UNCERTAIN (no exact restatement); LLM: SUPPORTED
# ─────────────────────────────────────────────────────────────────────────────

PARAPHRASE = [
    BenchmarkCase(
        source="HTTP is stateless and does not store session data.",
        claim="HTTP does not carry session state between requests.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="Faithful paraphrase of HTTP statelessness",
    ),
    BenchmarkCase(
        source="TCP retransmits lost packets to ensure reliable delivery.",
        claim="When a packet is lost, TCP resends it to guarantee it arrives.",
        expected_deterministic="unsupported",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="TCP retransmission paraphrased — 'guarantee' marker over-fires (known deterministic FP, safe content rejected)",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="DNS resolves domain names into IP addresses.",
        claim="DNS translates human-readable hostnames to numeric IP addresses.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="DNS paraphrased",
    ),
    BenchmarkCase(
        source="SSH encrypts all traffic between client and server.",
        claim="All communication over SSH is encrypted to protect confidentiality.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="SSH encryption paraphrased",
    ),
    BenchmarkCase(
        source="The OSI model has seven layers.",
        claim="The OSI reference model defines seven distinct layers.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="OSI layer count paraphrased",
    ),
    BenchmarkCase(
        source="DHCP automatically assigns IP addresses to devices on a network.",
        claim="Devices on a network receive their IP configuration automatically via DHCP.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="DHCP paraphrased",
    ),
    BenchmarkCase(
        source="NAT translates private IP addresses to public IP addresses.",
        claim="NAT enables multiple internal devices to share a single public IP.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="NAT paraphrased with synonymous explanation",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="VLANs logically segment a physical network into separate broadcast domains.",
        claim="By using VLANs, a single physical switch can host multiple isolated broadcast domains.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="VLANs paraphrased",
    ),
    BenchmarkCase(
        source="TLS provides encryption and authentication for web traffic.",
        claim="TLS secures web communication by encrypting data and verifying server identity.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="TLS paraphrased",
    ),
    BenchmarkCase(
        source="BGP is used to exchange routing information between autonomous systems.",
        claim="Autonomous systems communicate their routing tables to each other using BGP.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="BGP paraphrased",
    ),
    BenchmarkCase(
        source="FTP uses two separate channels for control and data.",
        claim="FTP maintains distinct connections for commands and file transfers.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="FTP channels paraphrased",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="ICMP is used to send error messages and operational information.",
        claim="Network devices use ICMP to report problems like unreachable destinations.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="ICMP paraphrased",
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# UNSUPPORTED (added absolute/universal claim not in source)
# Both deterministic and LLM: UNSUPPORTED
# ─────────────────────────────────────────────────────────────────────────────

UNSUPPORTED = [
    BenchmarkCase(
        source="TCP uses a three-way handshake to establish a connection.",
        claim="TCP guarantees zero packet loss for all connections.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="Absolute 'guarantees' not in source (marker detected)",
    ),
    BenchmarkCase(
        source="HTTP is stateless.",
        claim="HTTP never stores any state between requests.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="low",
        category="unsupported",
        description="Absolute 'never' not in source (marker detected)",
    ),
    BenchmarkCase(
        source="TCP uses a three-way handshake.",
        claim="TCP uses a three-way handshake and always succeeds.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="low",
        category="unsupported",
        description="Added 'always' (marker detected)",
    ),
    BenchmarkCase(
        source="DNS resolves domain names into IP addresses.",
        claim="DNS resolves domain names into IP addresses without any failures.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'without' is stopword — deterministic misses (no surviving markers), LLM rejects",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="SSH encrypts traffic between client and server.",
        claim="SSH is the only protocol that encrypts client-server traffic.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'only' marker now detected via raw tokens (was a documented miss)",
    ),
    BenchmarkCase(
        source="DHCP assigns IP addresses automatically.",
        claim="DHCP always assigns a unique IP address to every device.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'always' marker detected (both 'every' and 'always' are markers, 'every' filtered but 'always' survives)",
    ),
    BenchmarkCase(
        source="NAT translates private to public IP addresses.",
        claim="NAT eliminates the need for public IP addresses entirely.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'entirely' added to markers — deterministic now rejects (was a documented miss)",
    ),
    BenchmarkCase(
        source="TLS provides encryption for web traffic.",
        claim="TLS is the only encryption protocol used on the internet.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'only' marker now detected via raw tokens (was a documented miss)",
    ),
    BenchmarkCase(
        source="ICMP sends error messages.",
        claim="ICMP sends all error messages across the entire internet.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'all' is stopword, 'entire' not a marker — deterministic misses, LLM rejects",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="UDP provides fast, connectionless delivery.",
        claim="UDP is always faster than TCP under every condition.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'always' marker detected",
    ),
    BenchmarkCase(
        source="BGP exchanges routing information between autonomous systems.",
        claim="BGP is the only protocol that exchanges routing information between autonomous systems.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'only' marker now detected via raw tokens (was a documented miss)",
    ),
    BenchmarkCase(
        source="OSPF is a link-state routing protocol.",
        claim="OSPF is the only link-state routing protocol that exists.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'only' marker now detected via raw tokens (was a documented miss)",
    ),
    BenchmarkCase(
        source="VLANs segment a network into broadcast domains.",
        claim="VLANs guarantee complete security for all segmented networks.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'guarantee' marker detected",
    ),
    BenchmarkCase(
        source="ARP maps IP addresses to MAC addresses.",
        claim="ARP is the only mechanism for mapping IP to MAC addresses.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'only' marker now detected via raw tokens (was a documented miss)",
    ),
    BenchmarkCase(
        source="GRE creates virtual point-to-point tunnels.",
        claim="GRE tunnels are always reliable under every network condition.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'always' marker detected",
    ),
    BenchmarkCase(
        source="TTL prevents packets from circulating indefinitely.",
        claim="TTL prevents all packets from ever looping in any network.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'all' is stopword, no surviving markers — deterministic misses, LLM rejects",
    ),
    BenchmarkCase(
        source="FTP uses two channels for control and data.",
        claim="FTP is the only protocol that uses separate channels for control and data.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'only' marker now detected via raw tokens (was a documented pipeline miss)",
    ),
    BenchmarkCase(
        source="Ethernet operates at layer two of the OSI model.",
        claim="Ethernet exclusively operates at layer two and nowhere else.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="low",
        category="unsupported",
        description="'exclusively'/'nowhere' added to markers — deterministic now rejects (was a documented pass)",
    ),
    BenchmarkCase(
        source="802.11ac operates in the 5 GHz band.",
        claim="802.11ac always delivers maximum throughput in every environment.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'always' marker detected",
    ),
    BenchmarkCase(
        source="OSPF is a link-state routing protocol.",
        claim="OSPF reduces convergence time in all network topologies.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'all' is stopword — deterministic misses, LLM rejects",
    ),
    BenchmarkCase(
        source="DHCP assigns IP addresses automatically.",
        claim="DHCP eliminates all IP conflicts on any network.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="unsupported",
        description="'all' is stopword — deterministic misses, LLM rejects",
        deterministic_known_limitation=True,
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# CONTRADICTION (reversed predicate or antonym)
# Both deterministic and LLM: CONTRADICTED
# ─────────────────────────────────────────────────────────────────────────────

CONTRADICTION = [
    BenchmarkCase(
        source="TCP establishes a connection before data transfer.",
        claim="TCP destroys the connection before data transfer.",
        expected_deterministic="contradicted",
        expected_llm="contradicted",
        risk="high",
        category="contradiction",
        description="establishes→destroys antonym (in CONTRADICTION_PAIRS)",
    ),
    BenchmarkCase(
        source="Exercise improves cardiovascular fitness.",
        claim="Exercise prevents cardiovascular fitness.",
        expected_deterministic="contradicted",
        expected_llm="contradicted",
        risk="high",
        category="contradiction",
        description="improves→prevents antonym (in CONTRADICTION_PAIRS)",
    ),
    BenchmarkCase(
        source="HTTP maintains state on the server.",
        claim="HTTP does not maintain state on the server.",
        expected_deterministic="contradicted",
        expected_llm="contradicted",
        risk="low",
        category="contradiction",
        description="Direct negation — deterministic now catches it via negation/polarity flip",
    ),
    BenchmarkCase(
        source="TLS encrypts all web traffic.",
        claim="TLS does not encrypt web traffic.",
        expected_deterministic="contradicted",
        expected_llm="contradicted",
        risk="high",
        category="contradiction",
        description="Direct negation — deterministic now catches it via negation/polarity flip",
    ),
    BenchmarkCase(
        source="DNS resolves domain names to IP addresses.",
        claim="DNS converts IP addresses to domain names.",
        expected_deterministic="uncertain",
        expected_llm="contradicted",
        risk="high",
        category="contradiction",
        description="Reversed direction — deterministic misses (resolves/converts not in pairs), LLM catches it",
    ),
    BenchmarkCase(
        source="SSH authenticates the server to the client.",
        claim="SSH rejects the server during authentication.",
        expected_deterministic="uncertain",
        expected_llm="contradicted",
        risk="high",
        category="contradiction",
        description="Semantic reversal — deterministic misses (authenticates/rejects not in pairs), LLM catches it",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="OSPF increases network routing efficiency.",
        claim="OSPF prevents network routing efficiency.",
        expected_deterministic="contradicted",
        expected_llm="contradicted",
        risk="high",
        category="contradiction",
        description="increases→prevents antonym (in CONTRADICTION_PAIRS)",
    ),
    BenchmarkCase(
        source="DHCP assigns IP addresses dynamically.",
        claim="DHCP rejects dynamic IP address assignment.",
        expected_deterministic="uncertain",
        expected_llm="contradicted",
        risk="high",
        category="contradiction",
        description="Semantic reversal — deterministic misses (assigns/rejects not in pairs), LLM catches it",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="VLANs increase network segmentation.",
        claim="VLANs prevent network segmentation.",
        expected_deterministic="contradicted",
        expected_llm="contradicted",
        risk="high",
        category="contradiction",
        description="increase→prevent antonym (in CONTRADICTION_PAIRS)",
    ),
    BenchmarkCase(
        source="NAT supports multiple private-to-public mappings.",
        claim="NAT contradicts multiple private-to-public mappings.",
        expected_deterministic="contradicted",
        expected_llm="contradicted",
        risk="high",
        category="contradiction",
        description="supports→contradicts antonym (in CONTRADICTION_PAIRS)",
    ),
    BenchmarkCase(
        source="SYN packets are sent before the handshake completes.",
        claim="SYN packets are sent after the handshake completes.",
        expected_deterministic="unsupported",
        expected_llm="contradicted",
        risk="high",
        category="contradiction",
        description="Temporal reversal (before↔after) — deterministic temporal_reversal",
    ),
    BenchmarkCase(
        source="The handshake completes after the SYN packets are sent.",
        claim="SYN packets are sent before the handshake completes.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="paraphrase",
        description="Temporal mirror (consistent phrasing) — deterministic conservatively UNCERTAIN, NOT rejected",
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# VOCAB OVERLAP (shared words but swapped fact)
# Note: expected_deterministic = uncertain (below restatement threshold);
# expected_llm = unsupported (LLM detects the swapped fact).
# ─────────────────────────────────────────────────────────────────────────────

VOCAB_OVERLAP = [
    BenchmarkCase(
        source="Photosynthesis uses light energy to produce chemical energy.",
        claim="Photosynthesis uses light energy to produce nuclear energy.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="low",
        category="vocab_overlap",
        description="Same frame, swapped product (chemical→nuclear) — Test-C flag case",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="Chemical bonds store energy in molecules.",
        claim="Chemical bonds store energy through nuclear fission.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="vocab_overlap",
        description="Same words, swapped mechanism (bonds/fission)",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="TCP uses a three-way handshake to establish a connection.",
        claim="TCP uses a three-way handshake to establish a denial of service.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="vocab_overlap",
        description="Same words, swapped outcome (connection→denial of service)",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="HTTP uses TCP as its transport protocol.",
        claim="HTTP uses UDP as its transport protocol.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="vocab_overlap",
        description="Same frame, swapped entity (TCP→UDP)",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="DNS resolves domain names to IPv4 addresses.",
        claim="DNS resolves domain names to IPv6 addresses.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="vocab_overlap",
        description="IPv4/IPv6 numeric tokens preserved → containment drops below restatement → UNCERTAIN high-risk reject (was 'supported')",
    ),
    BenchmarkCase(
        source="SSH uses public key cryptography for authentication.",
        claim="SSH uses symmetric key cryptography for authentication.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="vocab_overlap",
        description="Same frame, swapped entity (public→symmetric)",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="ARP maps IP addresses to MAC addresses.",
        claim="ARP maps MAC addresses to IP addresses.",
        expected_deterministic="unsupported",
        expected_llm="contradicted",
        risk="low",
        category="vocab_overlap",
        description="Reversed direction — deterministic order-reversal now rejects it (was 'supported')",
    ),
    BenchmarkCase(
        source="OSPF calculates shortest path trees for routing.",
        claim="OSPF calculates longest path trees for routing.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="vocab_overlap",
        description="Same frame, swapped modifier (shortest→longest)",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="GRE encapsulates network packets for tunneling.",
        claim="GRE decapsulates network packets for tunneling.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="vocab_overlap",
        description="Same frame, swapped action (encapsulate→decapsulate)",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="FTP transfers files over TCP port 21.",
        claim="FTP transfers files over UDP port 21.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="vocab_overlap",
        description="Same frame, swapped transport (TCP→UDP)",
    ),
    BenchmarkCase(
        source="TLS uses RSA for key exchange during the handshake.",
        claim="TLS uses RSA for key exchange without the handshake.",
        expected_deterministic="contradicted",
        expected_llm="unsupported",
        risk="high",
        category="vocab_overlap",
        description="'without' negation — deterministic now rejects it via negation/polarity flip (was 'supported')",
    ),
    BenchmarkCase(
        source="VLANs reduce broadcast traffic by segmenting networks.",
        claim="VLANs reduce broadcast traffic by concentrating networks.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="vocab_overlap",
        description="Same frame, swapped action (segmenting→concentrating)",
        deterministic_known_limitation=True,
    ),
    BenchmarkCase(
        source="802.11ac uses channel bonding to increase throughput.",
        claim="802.11ac uses channel bonding to decrease throughput.",
        expected_deterministic="uncertain",
        expected_llm="contradicted",
        risk="high",
        category="vocab_overlap",
        description="Same frame, antonym action — deterministic misses (decrease not in pairs), LLM catches it",
    ),
    BenchmarkCase(
        source="Email servers relay messages from sender to recipient.",
        claim="Email servers relay messages from recipient to sender.",
        expected_deterministic="unsupported",
        expected_llm="contradicted",
        risk="low",
        category="vocab_overlap",
        description="Directional reversal (sender↔recipient) — deterministic order-reversal rejects it",
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# NUMERIC / CAUSAL (fabricated specific details)
# Both: UNSUPPORTED (markers or fabricated causal)
# ─────────────────────────────────────────────────────────────────────────────

NUMERIC_CAUSAL = [
    BenchmarkCase(
        source="TCP uses a three-way handshake.",
        claim="TCP uses exactly 7 handshakes to establish a connection.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Fabricated numeric detail",
    ),
    BenchmarkCase(
        source="HTTP is stateless and uses port 80.",
        claim="HTTP operates on port 3000.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Fabricated port number — deterministic uncertain (low containment, no markers), LLM rejects",
    ),
    BenchmarkCase(
        source="DNS resolves domain names into IP addresses.",
        claim="DNS uses exactly 443 steps to resolve a domain name.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Fabricated numeric process ('exactly' marker)",
    ),
    BenchmarkCase(
        source="Exercise improves cardiovascular health.",
        claim="Exercise causes cardiovascular disease in all humans.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Fabricated negative causal — 'all' is stopword, no surviving markers, deterministic uncertain",
    ),
    BenchmarkCase(
        source="SSH encrypts client-server communication.",
        claim="SSH encryption requires exactly 256-bit keys in every implementation.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Fabricated universal numeric requirement ('exactly' marker)",
    ),
    BenchmarkCase(
        source="VLANs segment networks into broadcast domains.",
        claim="VLANs increase throughput by exactly 200 percent.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Fabricated numeric benefit ('exactly' marker)",
    ),
    BenchmarkCase(
        source="OSPF uses link-state advertisements.",
        claim="OSPF causes network loops in all topologies.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Fabricated negative causal — 'all' is stopword, no surviving markers, deterministic uncertain",
    ),
    BenchmarkCase(
        source="DHCP assigns IP addresses automatically.",
        claim="DHCP always assigns IP addresses in under 10 milliseconds.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Fabricated timing constraint ('always' marker)",
    ),
    BenchmarkCase(
        source="GRE encapsulates network layer protocols.",
        claim="GRE tunneling causes 50 percent packet loss on average.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Fabricated negative numeric — no absolute markers, deterministic uncertain",
    ),
    BenchmarkCase(
        source="BGP exchanges routing information.",
        claim="BGP requires exactly 10 autonomous systems for convergence.",
        expected_deterministic="unsupported",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Fabricated numeric requirement ('exactly' marker)",
    ),
    BenchmarkCase(
        source="A bacterial enzyme completes 4 cycles per second.",
        claim="A bacterial enzyme completes 3 cycles per second.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Number substitution (3 vs 4 cycles) — deterministic UNCERTAIN high-risk reject",
    ),
    BenchmarkCase(
        source="The CPU operates at 5 GHz clock speed.",
        claim="The CPU operates at 5 MHz clock speed.",
        expected_deterministic="uncertain",
        expected_llm="unsupported",
        risk="high",
        category="numeric_causal",
        description="Unit substitution (GHz vs MHz) — deterministic UNCERTAIN high-risk reject",
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# EDUCATIONAL INJECTION DISCUSSION (must be accepted, not rejected)
# Both: SUPPORTED or UNCERTAIN low-risk → PASS
# ─────────────────────────────────────────────────────────────────────────────

EDUCATIONAL_INJECTION = [
    BenchmarkCase(
        source="Prompt injection is a security attack where adversaries embed instructions in user inputs. Defenses include input validation and sandboxing.",
        claim="Prompt injection attacks attempt to manipulate AI systems through embedded instructions.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="educational_injection",
        description="Legitimate discussion of prompt injection (low containment, UNCERTAIN+low → PASS)",
    ),
    BenchmarkCase(
        source="Social engineering exploits human psychology rather than technical vulnerabilities.",
        claim="Social engineering exploits human psychology to gain unauthorized access.",
        expected_deterministic="uncertain",
        expected_llm="supported",
        risk="low",
        category="educational_injection",
        description="Security topic (not injection) — low containment, UNCERTAIN+low → PASS",
    ),
    BenchmarkCase(
        source="SQL injection inserts malicious SQL code into application queries. Parameterized queries prevent this.",
        claim="SQL injection inserts malicious SQL code into queries.",
        expected_deterministic="supported",
        expected_llm="supported",
        risk="low",
        category="educational_injection",
        description="Legitimate discussion of SQL injection",
    ),
]


def get_all_cases() -> list[BenchmarkCase]:
    """Return the complete benchmark dataset."""
    return (
        RESTATED
        + PARAPHRASE
        + UNSUPPORTED
        + CONTRADICTION
        + VOCAB_OVERLAP
        + NUMERIC_CAUSAL
        + EDUCATIONAL_INJECTION
    )


def get_category_counts() -> dict[str, int]:
    """Return category → count mapping for test output."""
    counts: dict[str, int] = {}
    for case in get_all_cases():
        counts[case.category] = counts.get(case.category, 0) + 1
    return counts
