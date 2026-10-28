package io.vitaldock.companion

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.*
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import kotlin.math.ceil
import kotlin.reflect.KClass

class HealthReader(context: Context) {
    private val client = HealthConnectClient.getOrCreate(context)
    companion object {
        val TYPES: Map<String, KClass<out Record>> = linkedMapOf(
            "heart_rate" to HeartRateRecord::class,
            "resting_heart_rate" to RestingHeartRateRecord::class,
            "hrv_rmssd" to HeartRateVariabilityRmssdRecord::class,
            "sleep" to SleepSessionRecord::class,
            "spo2" to OxygenSaturationRecord::class,
            "respiratory_rate" to RespiratoryRateRecord::class,
            "steps" to StepsRecord::class,
            "weight" to WeightRecord::class,
            "body_fat" to BodyFatRecord::class,
            "body_temperature" to BodyTemperatureRecord::class,
            "distance" to DistanceRecord::class,
            "active_energy" to ActiveCaloriesBurnedRecord::class,
            "total_energy" to TotalCaloriesBurnedRecord::class
        )
        fun permission(metric: String) = HealthPermission.getReadPermission(TYPES.getValue(metric))
        val permissions: Set<String> get() = TYPES.keys.map { permission(it) }.toSet()
    }
    suspend fun status(): JSONObject {
        val granted = client.permissionController.getGrantedPermissions()
        return envelope().put("status", "connected").put("permissions", JSONObject().apply {
            TYPES.keys.forEach { put(it, permission(it) in granted) }
        }).put("background_read_granted", HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND in granted)
    }
    fun supportsBackground() = client.features.getFeatureStatus(
        HealthConnectFeatures.FEATURE_READ_HEALTH_DATA_IN_BACKGROUND
    ) == HealthConnectFeatures.FEATURE_STATUS_AVAILABLE

    suspend fun coverage(metrics: List<String>, start: Instant, end: Instant): JSONObject {
        val granted = client.permissionController.getGrantedPermissions()
        val result = JSONObject()
        for (metric in metrics) {
            require(metric in TYPES)
            if (permission(metric) !in granted) {
                result.put(metric, JSONObject().put("status", "not_granted"))
                continue
            }
            try {
                val page = readPage(metric, start, end, 1, null)
                val visible = page.first.any { BridgePolicy.allowedOrigin(it.metadata.dataOrigin.packageName) }
                result.put(metric, JSONObject().put("status", when {
                    visible -> "available"
                    page.second != null -> "continue_paging_to_check_sources"
                    else -> "no_records"
                }))
            } catch (_: SecurityException) {
                result.put(metric, JSONObject().put("status", "permission_denied"))
            }
        }
        return envelope().put("since", start.toString()).put("until", end.toString())
            .put("metrics", result).put("coverage_method", "first_page_presence_not_record_count")
    }
    suspend fun records(metric: String, start: Instant, end: Instant, limit: Int, cursor: String?): JSONObject {
        require(metric in TYPES)
        if (permission(metric) !in client.permissionController.getGrantedPermissions()) throw SecurityException()
        val (rows, next) = readPage(metric, start, end, limit, cursor)
        val allowed = rows.filter { BridgePolicy.allowedOrigin(it.metadata.dataOrigin.packageName) }
        val budget = (BridgePolicy.MAX_SAMPLES / maxOf(1, allowed.size)).coerceAtLeast(1)
        val records = JSONArray()
        allowed.forEach { records.put(serialize(it, budget)) }
        return envelope().put("status", if (allowed.isEmpty()) "no_records" else "available")
            .put("metric", metric).put("since", start.toString()).put("until", end.toString())
            .put("records", records).put("next_page_token", next ?: JSONObject.NULL)
            .put("result_truncated", next != null).put("excluded_records", rows.size - allowed.size)
            .put("aggregation", "raw_source_records_not_added_across_sources")
    }
    private suspend fun <T : Record> page(type: KClass<T>, start: Instant, end: Instant, limit: Int,
                                         cursor: String?): Pair<List<Record>, String?> {
        val response = client.readRecords(ReadRecordsRequest(
            recordType = type, timeRangeFilter = TimeRangeFilter.between(start, end),
            pageSize = limit, pageToken = cursor, ascendingOrder = false
        ))
        return response.records to response.pageToken
    }
    private suspend fun readPage(metric: String, start: Instant, end: Instant, limit: Int,
                                 cursor: String?) = page(TYPES.getValue(metric), start, end, limit, cursor)

    private fun serialize(record: Record, budget: Int): JSONObject = JSONObject().apply {
        put("id", record.metadata.id)
        put("source_package", record.metadata.dataOrigin.packageName)
        put("last_modified_at", record.metadata.lastModifiedTime.toString())
        put("recording_method", record.metadata.recordingMethod)
        when (record) {
            is HeartRateRecord -> {
                interval(record.startTime, record.endTime)
                val stride = maxOf(1, ceil(record.samples.size.toDouble() / budget).toInt())
                val points = JSONArray()
                record.samples.forEachIndexed { i, sample -> if (i % stride == 0) points.put(
                    JSONObject().put("at", sample.time.toString()).put("bpm", sample.beatsPerMinute)
                        .put("source_index", i)) }
                put("samples", points); put("original_sample_count", record.samples.size)
                put("sample_stride", stride); put("samples_truncated", stride > 1)
            }
            is SleepSessionRecord -> {
                interval(record.startTime, record.endTime)
                put("stages", JSONArray().apply { record.stages.forEach { stage -> put(
                    JSONObject().put("start", stage.startTime.toString()).put("end", stage.endTime.toString())
                        .put("stage", stage.stage)) } })
            }
            is StepsRecord -> { interval(record.startTime, record.endTime); put("count", record.count) }
            is DistanceRecord -> { interval(record.startTime, record.endTime); put("meters", record.distance.inMeters) }
            is ActiveCaloriesBurnedRecord -> { interval(record.startTime, record.endTime); put("kcal", record.energy.inKilocalories) }
            is TotalCaloriesBurnedRecord -> { interval(record.startTime, record.endTime); put("kcal", record.energy.inKilocalories) }
            is RestingHeartRateRecord -> { put("at", record.time.toString()); put("bpm", record.beatsPerMinute) }
            is HeartRateVariabilityRmssdRecord -> { put("at", record.time.toString()); put("rmssd_ms", record.heartRateVariabilityMillis) }
            is OxygenSaturationRecord -> { put("at", record.time.toString()); put("percent", record.percentage.value) }
            is RespiratoryRateRecord -> { put("at", record.time.toString()); put("breaths_per_minute", record.rate) }
            is WeightRecord -> { put("at", record.time.toString()); put("kg", record.weight.inKilograms) }
            is BodyFatRecord -> { put("at", record.time.toString()); put("percent", record.percentage.value) }
            is BodyTemperatureRecord -> { put("at", record.time.toString()); put("celsius", record.temperature.inCelsius) }
            else -> error("unsupported_record")
        }
    }
    private fun JSONObject.interval(start: Instant, end: Instant) {
        put("start", start.toString()); put("end", end.toString())
    }
    private fun envelope() = JSONObject().put("schema_version", "health-connect/1")
        .put("provider", "android_health_connect").put("fetched_at", Instant.now().toString())
        .put("freshness", "fresh_phone_database_read_does_not_force_source_app_sync")
}
