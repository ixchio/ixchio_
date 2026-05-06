"""
Pre-computed demo data for recruiter / portfolio showcasing.
Returns a perfect, comprehensive research report instantly without hitting any APIs
or waiting for the 60-second STORM pipeline.
"""

from datetime import datetime, timezone

DEMO_TASK_ID = "demo-task-0000-0000-0000"

DEMO_REPORT_MARKDOWN = """# The Impact of Quantum Computing on Modern Cryptography
## Executive Summary

Quantum computing represents a paradigm shift in computational power, posing an existential threat to the cryptographic protocols that secure the modern internet. While large-scale, fault-tolerant quantum computers do not yet exist, the theoretical framework—specifically Shor's Algorithm—proves that widely used public-key encryption (RSA, ECC) can be broken exponentially faster than on classical machines. This report synthesizes perspectives from cryptography, quantum physics, and cybersecurity policy to evaluate the timeline of the quantum threat and the industry's transition to Post-Quantum Cryptography (PQC).

---

## 1. The Core Threat: Shor's and Grover's Algorithms

At the heart of the quantum threat are two algorithms that dismantle the mathematical hardness assumptions underpinning current encryption:

*   **Shor's Algorithm:** Capable of factoring large prime numbers and solving discrete logarithms in polynomial time. This completely breaks **RSA, Diffie-Hellman, and Elliptic Curve Cryptography (ECC)**. A classical computer would take billions of years to break RSA-2048; a sufficiently powerful quantum computer could do it in hours.
*   **Grover's Algorithm:** Provides a quadratic speedup for unstructured search. While less devastating than Shor's, it halves the effective security of symmetric encryption. **AES-128 becomes vulnerable**, requiring an immediate industry upgrade to AES-256 to maintain adequate security margins.

> [!WARNING] "Harvest Now, Decrypt Later"
> Adversarial nation-states are currently intercepting and storing encrypted internet traffic. Even though they cannot decrypt it today, they will decrypt it retroactively once a Cryptographically Relevant Quantum Computer (CRQC) is built (Q-Day).

---

## 2. Timeline to Q-Day: Expert Consensus

The timeline for a CRQC capable of breaking RSA-2048 is highly debated. It requires not just physical qubits, but *logical* error-corrected qubits.

*   **Optimistic Estimates (5-10 years):** Driven by rapid advancements in neutral atom and superconducting qubit modalities (e.g., IBM, QuEra).
*   **Conservative Estimates (15-30 years):** Focus on the massive engineering challenges of quantum error correction and scaling control electronics.

Regardless of the timeline, the migration to quantum-resistant standards takes decades. The "Mosca Theorem" states that if the time required to migrate infrastructure plus the time data must remain secure is greater than the time until a quantum computer is built, organizations are already at critical risk.

---

## 3. The Solution: Post-Quantum Cryptography (PQC)

The National Institute of Standards and Technology (NIST) has finalized the first set of PQC standards designed to be secure against both quantum and classical adversaries. These algorithms rely on different mathematical foundations:

### Standardized Algorithms (August 2024)
1.  **FIPS 203 (ML-KEM):** Based on CRYSTALS-Kyber. The primary standard for Key Encapsulation (replacing RSA key exchange). Relies on Module Learning With Errors (MLWE), a lattice-based math problem.
2.  **FIPS 204 (ML-DSA):** Based on CRYSTALS-Dilithium. The primary standard for Digital Signatures.
3.  **FIPS 205 (SLH-DSA):** Based on SPHINCS+. A stateless hash-based signature scheme, acting as a conservative backup.

> [!TIP] Implementation
> These new algorithms generally require larger key sizes and signatures than RSA/ECC, causing challenges for constrained IoT devices and requiring network protocol updates (e.g., TLS 1.3 integration).

---

## 4. Industry Impact and Mitigation Strategy

The transition to PQC will be the largest cybersecurity upgrade in history.

1.  **Cryptographic Discovery:** Organizations must first map their cryptographic inventory. You cannot replace algorithms you don't know you are using.
2.  **Crypto-Agility:** Systems must be redesigned to allow algorithms to be swapped out without replacing the underlying hardware or protocol logic.
3.  **Hybrid Deployment:** In the interim period, systems will use a hybrid approach—combining a classical algorithm (like ECC) with a PQC algorithm (like ML-KEM) to ensure security even if the new math is later broken by classical means.

## Conclusion

Quantum computing is no longer purely theoretical. The finalization of NIST's PQC standards marks the beginning of a mandatory, multi-year migration. Security leaders must adopt crypto-agility and begin transitioning critical infrastructure immediately, operating under the assumption that long-term secrets are already being harvested by adversaries.
"""

DEMO_TASK_DATA = {
    "task_id": DEMO_TASK_ID,
    "status": "completed",
    "query": "impact of quantum computing on cryptography (DEMO)",
    "user": "recruiter@demo.com",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "progress": 100,
    "report": DEMO_REPORT_MARKDOWN,
    "stats": {
        "api_calls": 0,
        "cache_hits": 9,
        "errors": []
    },
    "current_step": "Demo successfully loaded."
}
