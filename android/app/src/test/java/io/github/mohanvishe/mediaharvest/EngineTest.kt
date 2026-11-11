package io.github.mohanvishe.mediaharvest

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EngineTest {
    @Test
    fun onlyPlainLinksReachTheEngine() {
        assertTrue(LINK.matches("https://www.youtube.com/watch?v=jNQXAC9IVRw"))
        assertTrue(LINK.matches("HTTP://example.com/a"))
        // Anything yt-dlp could read as an option, or that is not one link.
        assertFalse(LINK.matches("--exec rm -rf x"))
        assertFalse(LINK.matches("-o/sdcard/x https://example.com"))
        assertFalse(LINK.matches("https://a.com/x --exec y"))
        assertFalse(LINK.matches("file:///data/data/x"))
        assertFalse(LINK.matches("hello"))
    }

    @Test
    fun sharedTextGivesItsLink() {
        assertEquals("https://youtu.be/abc", LINK.find("Watch this https://youtu.be/abc now")?.value)
        assertEquals("https://youtu.be/abc", LINK.find("\"https://youtu.be/abc\"")?.value)
    }

    @Test
    fun titleDropsIdAndExtension() {
        assertEquals("Me at the zoo", Engine.titleOf("Me at the zoo [jNQXAC9IVRw].mp4"))
        assertEquals("Song [Live]", Engine.titleOf("Song [Live] [abc123].mp3"))
    }

    @Test
    fun reasonIsTheLastErrorLine() {
        val e = RuntimeException("[youtube] x: Downloading\nERROR: [youtube] x: Video unavailable\nWARNING: later")
        assertEquals("[youtube] x: Video unavailable", Engine.reason(e))
        assertEquals("plain failure", Engine.reason(RuntimeException("plain failure")))
    }
}
