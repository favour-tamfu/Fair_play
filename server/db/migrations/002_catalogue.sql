-- 002_catalogue (B-T04): sequential upload IDs S-000001…, faster per-song hash deletes, one hash set per song.
CREATE SEQUENCE song_upload_seq START 1;
CREATE INDEX fp_hashes_song ON fp_hashes(song_id);
CREATE INDEX songs_status ON songs(status);
