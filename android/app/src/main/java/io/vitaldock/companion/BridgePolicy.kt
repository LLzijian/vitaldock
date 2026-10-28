package io.vitaldock.companion

import java.security.MessageDigest
import java.time.Duration
import java.time.Instant

object BridgePolicy {
    const val PORT = 38765
    const val MAX_RECORDS = 200
    const val MAX_SAMPLES = 4000
    fun authorized(token: String, header: String?): Boolean =
        token.length == 64 && MessageDigest.isEqual(
            "Bearer $token".toByteArray(Charsets.UTF_8),
            (header ?: "").toByteArray(Charsets.UTF_8)
        )

    fun window(since: String?, until: String?): Pair<Instant, Instant> {
        val start = Instant.parse(since)
        val end = Instant.parse(until)
        require(end > start && Duration.between(start, end) <= Duration.ofDays(7))
        return start to end
    }
    fun limit(value: String?): Int = (value?.toInt() ?: 100).also {
        require(it in 1..MAX_RECORDS)
    }
    fun allowedOrigin(packageName: String): Boolean = packageName != "com.strava"
}
