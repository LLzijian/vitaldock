package io.vitaldock.companion

import android.content.Context
import fi.iki.elonen.NanoHTTPD
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject

class BridgeServer(context: Context, private val token: String) : NanoHTTPD("127.0.0.1", BridgePolicy.PORT) {
    private val reader = HealthReader(context)
    override fun serve(session: IHTTPSession): Response {
        if (!BridgePolicy.authorized(token, session.headers["authorization"])) return failure(Response.Status.UNAUTHORIZED, "unauthorized")
        if (session.method != Method.GET) return failure(Response.Status.METHOD_NOT_ALLOWED, "get_only")
        return try {
            val result = runBlocking { withTimeout(25000) {
                if (session.uri == "/status") return@withTimeout reader.status()
                val p = session.parameters.mapValues { it.value.firstOrNull() }
                val (start, end) = BridgePolicy.window(p["since"], p["until"])
                when (session.uri) {
                    "/coverage" -> reader.coverage(p["metrics"]?.split(',') ?: HealthReader.TYPES.keys.toList(), start, end)
                    "/records" -> {
                        val cursor = p["cursor"]?.also { require(it.length <= 4096) }
                        reader.records(requireNotNull(p["metric"]), start, end, BridgePolicy.limit(p["limit"]), cursor)
                    }
                    else -> return@withTimeout null
                }
            } }
            if (result == null) failure(Response.Status.NOT_FOUND, "not_found")
            else newFixedLengthResponse(Response.Status.OK, "application/json", result.toString())
                .apply { addHeader("Cache-Control", "no-store") }
        } catch (_: SecurityException) { failure(Response.Status.FORBIDDEN, "permission_denied")
        } catch (_: IllegalArgumentException) { failure(Response.Status.BAD_REQUEST, "invalid_arguments")
        } catch (_: Exception) { failure(Response.Status.INTERNAL_ERROR, "phone_read_failed") }
    }
    private fun failure(status: Response.Status, code: String) = newFixedLengthResponse(
        status, "application/json", JSONObject().put("error", code).toString()
    ).apply { addHeader("Cache-Control", "no-store") }
}
