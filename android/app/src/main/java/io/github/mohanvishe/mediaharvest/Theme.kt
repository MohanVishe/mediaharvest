package io.github.mohanvishe.mediaharvest

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

// The web app's Mono theme (ui/src/_mh-mono.sass): one monospace face, quiet
// greys, one teal for progress and the main button. Light or dark as the
// phone is set.

private val Light = lightColorScheme(
    primary = Color(0xFF0F766E), onPrimary = Color.White,
    background = Color(0xFFF6F7F6), onBackground = Color(0xFF141917),
    surface = Color(0xFFFFFFFF), onSurface = Color(0xFF141917),
    surfaceVariant = Color(0xFFEFF1F0), onSurfaceVariant = Color(0xFF4A5450),
    surfaceContainer = Color(0xFFFFFFFF), surfaceContainerHigh = Color(0xFFFFFFFF),
    outline = Color(0xFF6F7B76), outlineVariant = Color(0x1F101816),
    inverseSurface = Color(0xFF141917), inverseOnSurface = Color(0xFFF6F7F6),
)

private val Dark = darkColorScheme(
    primary = Color(0xFF2DD4BF), onPrimary = Color(0xFF0E1110),
    background = Color(0xFF0E1110), onBackground = Color(0xFFDFE7E3),
    surface = Color(0xFF141817), onSurface = Color(0xFFDFE7E3),
    surfaceVariant = Color(0xFF1B201E), onSurfaceVariant = Color(0xFF9AA7A1),
    surfaceContainer = Color(0xFF141817), surfaceContainerHigh = Color(0xFF1B201E),
    outline = Color(0xFF6D7A74), outlineVariant = Color(0x1AD6ECE4),
    inverseSurface = Color(0xFFDFE7E3), inverseOnSurface = Color(0xFF0E1110),
)

private val Mono = FontFamily(
    Font(R.font.jetbrains_mono_regular, FontWeight.Normal),
    Font(R.font.jetbrains_mono_medium, FontWeight.Medium),
)

private val Type = Typography().run {
    Typography(
        displayLarge = displayLarge.copy(fontFamily = Mono), displayMedium = displayMedium.copy(fontFamily = Mono),
        displaySmall = displaySmall.copy(fontFamily = Mono), headlineLarge = headlineLarge.copy(fontFamily = Mono),
        headlineMedium = headlineMedium.copy(fontFamily = Mono), headlineSmall = headlineSmall.copy(fontFamily = Mono),
        titleLarge = titleLarge.copy(fontFamily = Mono), titleMedium = titleMedium.copy(fontFamily = Mono),
        titleSmall = titleSmall.copy(fontFamily = Mono), bodyLarge = bodyLarge.copy(fontFamily = Mono),
        bodyMedium = bodyMedium.copy(fontFamily = Mono), bodySmall = bodySmall.copy(fontFamily = Mono),
        labelLarge = labelLarge.copy(fontFamily = Mono), labelMedium = labelMedium.copy(fontFamily = Mono),
        labelSmall = labelSmall.copy(fontFamily = Mono),
    )
}

private val Square = Shapes(
    extraSmall = RoundedCornerShape(3.dp), small = RoundedCornerShape(3.dp),
    medium = RoundedCornerShape(4.dp), large = RoundedCornerShape(6.dp), extraLarge = RoundedCornerShape(6.dp),
)

@Composable
fun MonoTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, typography = Type, shapes = Square, content = content)
}
