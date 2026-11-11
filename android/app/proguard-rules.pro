# The download engine (youtubedl-android) is small and starts its parts by
# name; keep it whole. Its helpers also load classes by reflection: Jackson
# (reads GitHub replies in the updater) and commons-compress (unpacks Python
# and FFmpeg on first start), so they stay whole too.
-keep class com.yausername.** { *; }
-keep class com.fasterxml.jackson.** { *; }
-keep class org.apache.commons.compress.archivers.zip.** { *; }
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod

# Jackson reads these Java bean annotations when present; Android has none.
-dontwarn java.beans.ConstructorProperties
-dontwarn java.beans.Transient
