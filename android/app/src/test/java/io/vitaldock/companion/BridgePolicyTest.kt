package io.vitaldock.companion

import org.junit.Assert.*
import org.junit.Test

class BridgePolicyTest {
    private val token = "a".repeat(64)
    @Test fun authenticationFailsClosed() {
        assertTrue(BridgePolicy.authorized(token, "Bearer $token"))
        assertFalse(BridgePolicy.authorized("", null))
        assertFalse(BridgePolicy.authorized(token, null))
        assertFalse(BridgePolicy.authorized(token, "Bearer ${"b".repeat(64)}"))
    }
    @Test fun boundedWindowsAndLimits() {
        BridgePolicy.window("2026-10-20T00:00:00Z", "2026-10-27T00:00:00Z")
        assertThrows(IllegalArgumentException::class.java) {
            BridgePolicy.window("2026-10-20T00:00:00Z", "2026-10-28T00:00:00Z")
        }
        assertThrows(IllegalArgumentException::class.java) { BridgePolicy.limit("201") }
        assertThrows(IllegalArgumentException::class.java) { BridgePolicy.limit("0") }
    }
    @Test fun excludesStravaOrigin() {
        assertFalse(BridgePolicy.allowedOrigin("com.strava"))
        assertTrue(BridgePolicy.allowedOrigin("com.example.synthetic"))
    }
}
