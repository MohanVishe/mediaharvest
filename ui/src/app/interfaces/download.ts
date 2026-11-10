// Compressing a finished video (app/compress.py, DownloadQueue.compress).
export interface Compression {
  state: 'running' | 'done' | 'kept' | 'error';
  preset: string;
  // The resolution it was limited to (720 means 720p), or none.
  height?: number | null;
  percent?: number;
  eta?: number | null;
  original_size?: number;
  size?: number;
  msg?: string;
}

export interface Download {
  id: string;
  title: string;
  url: string;
  download_type: string;
  codec?: string;
  quality: string;
  format: string;
  folder: string;
  custom_name_prefix: string;
  playlist_item_limit: number;
  split_by_chapters?: boolean;
  sponsorblock?: boolean;
  audio_tags?: string;
  chapter_template?: string;
  subtitle_language?: string;
  subtitle_mode?: string;
  ytdl_options_presets?: string[];
  ytdl_options_overrides?: Record<string, unknown>;
  clip_start?: number;
  clip_end?: number;
  live_status?: string;
  live_release_timestamp?: number;
  status: string;
  msg: string;
  percent: number;
  speed: number;
  eta: number;
  filename: string;
  checked: boolean;
  timestamp?: number;
  size?: number;
  error?: string;
  deleting?: boolean;
  chapter_files?: { filename: string, size: number }[];
  // Video only: compress preset chosen at download (off, light, medium, strong).
  compress?: string;
  // With compress: keep, or a height such as 720.
  compress_height?: string;
  // Set while and after the finished video is compressed (app/compress.py).
  compression?: Compression | null;
}
