import com.healthmarketscience.jackcess.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/**
 * VSB to CSV exporter using Jackcess.
 * Unlike mdb-export, this only reads active (non-deleted) rows
 * and sorts by SongNum.
 */
public class VsbToCsv {

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.out.println("Usage: java VsbToCsv <input.vsb> [output.csv]");
            System.exit(1);
        }

        String vsbPath = args[0];
        String csvPath = args.length >= 2 ? args[1] : vsbPath.replaceAll("\\.[^.]+$", "") + ".csv";

        System.out.println("Reading: " + vsbPath);

        List<String[]> songs = new ArrayList<>();

        try (Database db = DatabaseBuilder.open(new File(vsbPath))) {
            Table songsTable = db.getTable("Songs");
            if (songsTable == null) {
                System.err.println("Error: No 'Songs' table found");
                System.exit(1);
            }

            Cursor cursor = CursorBuilder.createCursor(songsTable);
            while (cursor.moveToNextRow()) {
                Row row = cursor.getCurrentRow();
                String title = (String) row.get("Title");
                if (title == null || title.startsWith("_")) continue;

                String songNum = String.valueOf(row.get("SongNum") != null ? ((Number) row.get("SongNum")).intValue() : 0);
                String body = row.get("Body") != null ? row.get("Body").toString() : "";
                String author = row.get("Author") != null ? row.get("Author").toString() : "";
                String copyright = row.get("Copyright") != null ? row.get("Copyright").toString() : "";
                String key = row.get("Key") != null ? row.get("Key").toString() : "";
                String categoryId = row.get("CategoryId") != null ? String.valueOf(((Number) row.get("CategoryId")).intValue()) : "1";

                songs.add(new String[]{songNum, title.trim(), body.trim(), author.trim(), copyright.trim(), key.trim(), categoryId});
            }
        }

        // Sort by SongNum
        songs.sort((a, b) -> {
            try { return Integer.compare(Integer.parseInt(a[0]), Integer.parseInt(b[0])); }
            catch (NumberFormatException e) { return a[0].compareTo(b[0]); }
        });

        // Write CSV
        try (BufferedWriter bw = new BufferedWriter(new OutputStreamWriter(new FileOutputStream(csvPath), StandardCharsets.UTF_8))) {
            bw.write("Nummer;Tittel;Tekst;Tekstforfatter;Copyright;Toneart;Kategori");
            bw.newLine();
            for (String[] song : songs) {
                StringBuilder line = new StringBuilder();
                for (int i = 0; i < song.length; i++) {
                    if (i > 0) line.append(';');
                    String val = song[i];
                    if (val.contains(";") || val.contains("\"") || val.contains("\n") || val.contains("\r")) {
                        line.append('"').append(val.replace("\"", "\"\"")).append('"');
                    } else {
                        line.append(val);
                    }
                }
                bw.write(line.toString());
                bw.newLine();
            }
        }

        System.out.println("Exported " + songs.size() + " songs to " + csvPath);
    }
}
