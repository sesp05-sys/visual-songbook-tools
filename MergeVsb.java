import com.healthmarketscience.jackcess.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/**
 * Slår sammen flere VSB-filer til én.
 * Sangnummerering fortsetter sekvensielt mellom filene.
 *
 * Bruk: java MergeVsb output.vsb input1.vsb input2.vsb [input3.vsb ...]
 */
public class MergeVsb {

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            System.out.println("Usage: java MergeVsb <output.vsb> [--start N] [--keep-numbers] <input1.vsb> <input2.vsb> [...]");
            System.exit(1);
        }

        String outputPath = args[0];
        boolean renumber = true;
        int startNum = 1;
        List<String> inputPaths = new ArrayList<>();

        for (int i = 1; i < args.length; i++) {
            if ("--start".equals(args[i]) && i + 1 < args.length) {
                try { startNum = Math.max(1, Integer.parseInt(args[++i])); } catch (NumberFormatException e) {}
            } else if ("--keep-numbers".equals(args[i])) {
                renumber = false;
            } else {
                inputPaths.add(args[i]);
            }
        }

        if (inputPaths.size() < 2) {
            System.err.println("Error: at least 2 input files required");
            System.exit(1);
        }

        String templatePath = inputPaths.get(0);

        System.out.println("Slår sammen " + inputPaths.size() + " filer...");

        // Collect songs grouped by file (preserving file boundary)
        List<List<Map<String, Object>>> filesSongs = new ArrayList<>();

        for (String path : inputPaths) {
            System.out.println("  Leser: " + path);
            try (Database db = DatabaseBuilder.open(new File(path))) {
                Table songs = db.getTable("Songs");
                if (songs == null) {
                    System.err.println("    FEIL: Ingen 'Songs'-tabell funnet i " + path + ", hopper over.");
                    continue;
                }

                List<Map<String, Object>> fileSongs = new ArrayList<>();
                for (Row row : songs) {
                    String title = (String) row.get("Title");
                    if (title != null && !title.startsWith("_")) {
                        fileSongs.add(new LinkedHashMap<>(row));
                    }
                }

                // Sort by SongNum within each file
                fileSongs.sort((a, b) -> Integer.compare(toInt(a.get("SongNum")), toInt(b.get("SongNum"))));

                System.out.println("    " + fileSongs.size() + " songs");
                filesSongs.add(fileSongs);
            }
        }

        int totalSongs = filesSongs.stream().mapToInt(List::size).sum();
        System.out.println("Total: " + totalSongs + " songs");

        // Apply numbering strategy
        // - renumber=true: sequential numbering starting at startNum across all files
        // - renumber=false: book 1 keeps its numbers; subsequent books are offset to continue
        //   from (max num in previous book + 1)
        List<Map<String, Object>> allSongs = new ArrayList<>();
        if (renumber) {
            int n = startNum;
            for (List<Map<String, Object>> fs : filesSongs) {
                for (Map<String, Object> s : fs) {
                    s.put("__num", n++);
                    allSongs.add(s);
                }
            }
        } else {
            int offset = 0;
            int prevMaxOriginal = 0;
            int runningMax = 0;
            boolean first = true;
            for (List<Map<String, Object>> fs : filesSongs) {
                int fileMin = fs.stream().mapToInt(s -> toInt(s.get("SongNum"))).min().orElse(1);
                int fileMax = fs.stream().mapToInt(s -> toInt(s.get("SongNum"))).max().orElse(0);
                if (first) {
                    offset = 0;
                    first = false;
                } else {
                    // Shift this file so its minimum becomes (runningMax + 1)
                    offset = runningMax + 1 - fileMin;
                }
                for (Map<String, Object> s : fs) {
                    int num = toInt(s.get("SongNum")) + offset;
                    s.put("__num", num);
                    allSongs.add(s);
                    if (num > runningMax) runningMax = num;
                }
            }
        }

        // Copy template
        File outputFile = new File(outputPath);
        Files.copy(new File(templatePath).toPath(), outputFile.toPath(),
                StandardCopyOption.REPLACE_EXISTING);

        // Open and replace songs
        try (Database db = DatabaseBuilder.open(outputFile)) {
            Table songsTable = db.getTable("Songs");

            // Delete all existing rows
            int totalDeleted = 0;
            int passDeleted;
            do {
                passDeleted = 0;
                Cursor cursor = CursorBuilder.createCursor(songsTable);
                while (cursor.moveToNextRow()) {
                    cursor.deleteCurrentRow();
                    passDeleted++;
                }
                totalDeleted += passDeleted;
            } while (passDeleted > 0);
            System.out.println("  Slettet " + totalDeleted + " rader");

            // Insert dummy song
            Date now = new Date();
            String dummyTitle = "__________________________________________________";
            String dummyBody = ".                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           .\n\n.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           .";
            songsTable.addRow(1, 0, dummyTitle, dummyBody, now, dummyTitle + " " + dummyBody, "", "", "C", 1);

            // Insert songs with computed numbering
            int songId = 2;
            for (Map<String, Object> song : allSongs) {
                String title = getString(song, "Title");
                String body = getString(song, "Body");
                String author = getString(song, "Author");
                String copyright = getString(song, "Copyright");
                String key = getString(song, "Key");
                int categoryId = toInt(song.get("CategoryId"));
                if (categoryId == 0) categoryId = 1;
                String search = title + " " + body;
                int songNum = toInt(song.get("__num"));

                songsTable.addRow(songId, songNum, title, body, now, search, copyright, author, key, categoryId);
                songId++;
            }
        }
        System.out.println("Done! " + allSongs.size() + " songs written to " + outputPath);
    }

    static int toInt(Object val) {
        if (val == null) return 0;
        if (val instanceof Number) return ((Number) val).intValue();
        try { return Integer.parseInt(val.toString().trim()); } catch (Exception e) { return 0; }
    }

    static String getString(Map<String, Object> row, String key) {
        Object val = row.get(key);
        return val != null ? val.toString() : "";
    }
}
