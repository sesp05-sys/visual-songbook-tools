import com.healthmarketscience.jackcess.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/**
 * CSV til VSB (VideoPsalm) konverter.
 * Kopierer en eksisterende .vsb som mal og erstatter sangene fra CSV.
 *
 * Supports flexible CSV column names (Norwegian and English):
 *   Required: Title/Tittel
 *   Optional: Number/Nummer, Text/Tekst/Body/Lyrics, Author/Tekstforfatter,
 *             Copyright, Key/Toneart, Category/Kategori
 *
 * Auto-detects delimiter (semicolon or comma).
 */
public class CsvToVsb {

    static final String[] DEFAULT_TEMPLATES = {
        "template.vsb"
    };

    // VSB format key (obfuscated) - required for compatibility with the host application
    private static String getFormatKey() {
        int[] d = {82,97,110,105,115,104,97,80,51};
        StringBuilder sb = new StringBuilder();
        for (int c : d) sb.append((char) c);
        return sb.toString();
    }

    // Column name aliases mapped to canonical field names
    static final Map<String, String> COLUMN_ALIASES = new LinkedHashMap<>();
    static {
        // Number
        for (String s : new String[]{"nummer", "number", "num", "songnum", "nr", "#", "no"})
            COLUMN_ALIASES.put(s, "number");
        // Title
        for (String s : new String[]{"tittel", "title", "name", "sang", "song"})
            COLUMN_ALIASES.put(s, "title");
        // Body/Lyrics
        for (String s : new String[]{"tekst", "text", "body", "lyrics", "words", "sangtekst"})
            COLUMN_ALIASES.put(s, "body");
        // Author
        for (String s : new String[]{"tekstforfatter", "author", "forfatter", "writer", "artist"})
            COLUMN_ALIASES.put(s, "author");
        // Copyright
        for (String s : new String[]{"copyright", "rettigheter"})
            COLUMN_ALIASES.put(s, "copyright");
        // Key
        for (String s : new String[]{"toneart", "key", "tone"})
            COLUMN_ALIASES.put(s, "key");
        // Category
        for (String s : new String[]{"kategori", "category", "cat", "type", "genre"})
            COLUMN_ALIASES.put(s, "category");
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.out.println("Usage: java CsvToVsb <input.csv> [output.vsb] [--template template.vsb]");
            System.exit(1);
        }

        String csvPath = null;
        String vsbPath = null;
        String templatePath = null;

        for (int i = 0; i < args.length; i++) {
            if ("--template".equals(args[i]) && i + 1 < args.length) {
                templatePath = args[++i];
            } else if (csvPath == null) {
                csvPath = args[i];
            } else if (vsbPath == null) {
                vsbPath = args[i];
            }
        }

        if (csvPath == null) {
            System.out.println("Usage: java CsvToVsb <input.csv> [output.vsb] [--template template.vsb]");
            System.exit(1);
        }

        if (vsbPath == null) {
            vsbPath = csvPath.replaceAll("\\.[^.]+$", "") + ".vsb";
        }

        if (templatePath == null) {
            for (String t : DEFAULT_TEMPLATES) {
                if (new File(t).exists()) {
                    templatePath = t;
                    break;
                }
            }
        }

        System.out.println("Reading CSV: " + csvPath);
        CsvData csvData = readCsv(csvPath);

        if (csvData.columnMap.get("title") == null) {
            System.err.println("Error: CSV must have a 'Title' (or 'Tittel') column.");
            System.err.println("Found columns: " + csvData.headerNames);
            System.err.println("Recognized mappings: " + csvData.columnMap);
            System.exit(1);
        }

        System.out.println("Found " + csvData.rows.size() + " songs");
        System.out.println("Column mapping: " + csvData.columnMap);

        File vsbFile = new File(vsbPath);
        boolean createdFromScratch = false;

        if (templatePath != null && new File(templatePath).exists()) {
            // Copy template
            System.out.println("Using template: " + templatePath);
            Files.copy(new File(templatePath).toPath(), vsbFile.toPath(),
                    StandardCopyOption.REPLACE_EXISTING);
        } else {
            // Create from scratch
            System.out.println("No template found — creating new VSB database");
            createdFromScratch = true;
            if (vsbFile.exists()) vsbFile.delete();
            Database newDb = new DatabaseBuilder(vsbFile)
                    .setFileFormat(Database.FileFormat.V2000)
                    .create();
            // Create all required tables
            new TableBuilder("Songs")
                .addColumn(new ColumnBuilder("SongID", DataType.LONG))
                .addColumn(new ColumnBuilder("SongNum", DataType.INT))
                .addColumn(new ColumnBuilder("Title", DataType.TEXT).setLengthInUnits(50))
                .addColumn(new ColumnBuilder("Body", DataType.MEMO))
                .addColumn(new ColumnBuilder("Modified", DataType.SHORT_DATE_TIME))
                .addColumn(new ColumnBuilder("Search", DataType.MEMO))
                .addColumn(new ColumnBuilder("Copyright", DataType.TEXT).setLengthInUnits(100))
                .addColumn(new ColumnBuilder("Author", DataType.TEXT).setLengthInUnits(100))
                .addColumn(new ColumnBuilder("Key", DataType.TEXT).setLengthInUnits(200))
                .addColumn(new ColumnBuilder("CategoryId", DataType.LONG))
                .toTable(newDb);
            new TableBuilder("Categories")
                .addColumn(new ColumnBuilder("ID", DataType.LONG))
                .addColumn(new ColumnBuilder("Name", DataType.TEXT).setLengthInUnits(50))
                .toTable(newDb);
            new TableBuilder("Version")
                .addColumn(new ColumnBuilder("Version", DataType.LONG))
                .addColumn(new ColumnBuilder("Revision", DataType.LONG))
                .addColumn(new ColumnBuilder("Build", DataType.LONG))
                .addColumn(new ColumnBuilder("InstalledOn", DataType.SHORT_DATE_TIME))
                .toTable(newDb);
            new TableBuilder("SongBooks")
                .addColumn(new ColumnBuilder("BookID", DataType.LONG))
                .addColumn(new ColumnBuilder("Title", DataType.TEXT).setLengthInUnits(50))
                .addColumn(new ColumnBuilder("StartingNumber", DataType.LONG))
                .addColumn(new ColumnBuilder("EndingNumber", DataType.LONG))
                .toTable(newDb);
            new TableBuilder("History")
                .addColumn(new ColumnBuilder("SongID", DataType.LONG))
                .addColumn(new ColumnBuilder("DateAccessed", DataType.SHORT_DATE_TIME))
                .addColumn(new ColumnBuilder("TimeAccessed", DataType.SHORT_DATE_TIME))
                .toTable(newDb);
            new TableBuilder("CurrentSong")
                .addColumn(new ColumnBuilder("SongID", DataType.LONG))
                .addColumn(new ColumnBuilder("Paragraph", DataType.TEXT).setLengthInUnits(50))
                .addColumn(new ColumnBuilder("Modified", DataType.SHORT_DATE_TIME))
                .addColumn(new ColumnBuilder("DisplayedOn", DataType.SHORT_DATE_TIME))
                .toTable(newDb);
            new TableBuilder("PageSetup")
                .addColumn(new ColumnBuilder("FontName", DataType.TEXT).setLengthInUnits(30))
                .addColumn(new ColumnBuilder("FontSize", DataType.FLOAT))
                .addColumn(new ColumnBuilder("FontBold", DataType.BOOLEAN))
                .addColumn(new ColumnBuilder("FontItalic", DataType.BOOLEAN))
                .addColumn(new ColumnBuilder("ForeColor", DataType.LONG))
                .addColumn(new ColumnBuilder("MarginTop", DataType.FLOAT))
                .addColumn(new ColumnBuilder("MarginLeft", DataType.FLOAT))
                .addColumn(new ColumnBuilder("MarginRight", DataType.FLOAT))
                .addColumn(new ColumnBuilder("MarginBottom", DataType.FLOAT))
                .addColumn(new ColumnBuilder("BackColor", DataType.LONG))
                .addColumn(new ColumnBuilder("Top", DataType.INT))
                .addColumn(new ColumnBuilder("Left", DataType.INT))
                .addColumn(new ColumnBuilder("Height", DataType.INT))
                .addColumn(new ColumnBuilder("Width", DataType.INT))
                .toTable(newDb);
            new TableBuilder("Export")
                .addColumn(new ColumnBuilder("SongNum", DataType.INT))
                .addColumn(new ColumnBuilder("Title", DataType.TEXT).setLengthInUnits(50))
                .addColumn(new ColumnBuilder("Key", DataType.TEXT).setLengthInUnits(10))
                .addColumn(new ColumnBuilder("Body", DataType.MEMO))
                .addColumn(new ColumnBuilder("BookName", DataType.TEXT).setLengthInUnits(50))
                .addColumn(new ColumnBuilder("VerseLine", DataType.TEXT).setLengthInUnits(255))
                .addColumn(new ColumnBuilder("ChorusLine", DataType.TEXT).setLengthInUnits(255))
                .addColumn(new ColumnBuilder("TitleSort", DataType.TEXT).setLengthInUnits(255))
                .addColumn(new ColumnBuilder("VerseSort", DataType.TEXT).setLengthInUnits(255))
                .addColumn(new ColumnBuilder("ChorusSort", DataType.TEXT).setLengthInUnits(255))
                .addColumn(new ColumnBuilder("Category", DataType.TEXT).setLengthInUnits(50))
                .toTable(newDb);
            new TableBuilder("Import")
                .addColumn(new ColumnBuilder("SongNum", DataType.TEXT).setLengthInUnits(4))
                .addColumn(new ColumnBuilder("Body", DataType.MEMO))
                .addColumn(new ColumnBuilder("Modified", DataType.SHORT_DATE_TIME))
                .addColumn(new ColumnBuilder("Key", DataType.TEXT).setLengthInUnits(10))
                .addColumn(new ColumnBuilder("Title", DataType.TEXT).setLengthInUnits(50))
                .toTable(newDb);
            // Insert default metadata
            newDb.getTable("Categories").addRow(1, "General");
            newDb.getTable("Version").addRow(2, 0, 7, new Date());
            newDb.getTable("SongBooks").addRow(1, "General", 1, null);
            newDb.getTable("PageSetup").addRow("Arial Rounded MT Bold", 20.25f, true, false, 16777215, 0f, 144f, 144f, 7200f, 0, 0, 10, 40, 620);
            newDb.getTable("PageSetup").addRow("Arial Rounded MT Bold", 32.25f, true, false, 16777215, 288f, 600f, 600f, 3168f, 0, 60, 10, 360, 620);
            newDb.getTable("PageSetup").addRow("Arial Rounded MT Bold", 18f, true, false, 16777215, 216f, 0f, 300f, 1200f, 0, 440, 10, 40, 620);
            newDb.close();
        }

        int count = 0;
        try (Database db = DatabaseBuilder.open(vsbFile)) {
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
            System.out.println("Deleted " + totalDeleted + " existing rows");

            // Dummy song (SongID=1) as VideoPsalm expects
            Date now = new Date();
            String dummyTitle = "__________________________________________________";
            String dummyBody = ".                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           .\n\n.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           .";
            songsTable.addRow(1, 0, dummyTitle, dummyBody, now, dummyTitle + " " + dummyBody, "", "", "C", 1);

            // Insert songs from CSV
            Map<String, Integer> colMap = csvData.columnMap;
            for (List<String> row : csvData.rows) {
                int songId = count + 2;
                int songNum = getInt(row, colMap.get("number"), songId - 1);
                String title = get(row, colMap.get("title"));
                String body = get(row, colMap.get("body"));
                String author = get(row, colMap.get("author"));
                String copyright = get(row, colMap.get("copyright"));
                String key = get(row, colMap.get("key"));
                int categoryId = getInt(row, colMap.get("category"), 1);

                if (title.isEmpty()) continue; // skip empty rows

                String search = title + " " + body;
                songsTable.addRow(songId, songNum, title, body, now, search, copyright, author, key, categoryId);
                count++;
            }
        }

        // Set format key for host application compatibility (only needed for new databases)
        if (createdFromScratch) {
            setJet4Password(vsbFile, getFormatKey());
        }

        System.out.println("Done! " + count + " songs written to " + vsbPath);
    }

    /** Sets password in JET4 database by XOR-encoding UTF-16LE into the header. */
    static void setJet4Password(File dbFile, String password) throws IOException {
        int pwOffset = 66;
        byte[] pwUtf16 = password.getBytes(StandardCharsets.UTF_16LE);
        try (RandomAccessFile raf = new RandomAccessFile(dbFile, "rw")) {
            raf.seek(pwOffset);
            byte[] area = new byte[pwUtf16.length];
            raf.read(area);
            for (int i = 0; i < pwUtf16.length; i++) {
                area[i] = (byte)(area[i] ^ pwUtf16[i]);
            }
            raf.seek(pwOffset);
            raf.write(area);
        }
    }

    static String get(List<String> row, Integer idx) {
        if (idx == null || idx < 0 || idx >= row.size()) return "";
        return row.get(idx).trim();
    }

    static int getInt(List<String> row, Integer idx, int defaultVal) {
        String s = get(row, idx);
        if (s.isEmpty()) return defaultVal;
        try { return Integer.parseInt(s); } catch (Exception e) { return defaultVal; }
    }

    // --- CSV parsing with header mapping ---

    static class CsvData {
        Map<String, Integer> columnMap; // canonical name -> column index
        List<String> headerNames;       // original header names
        List<List<String>> rows;
    }

    static CsvData readCsv(String path) throws IOException {
        String content = new String(Files.readAllBytes(Paths.get(path)), StandardCharsets.UTF_8);
        CsvData data = new CsvData();
        data.rows = new ArrayList<>();

        int pos = 0;
        int headerEnd = content.indexOf('\n');
        if (headerEnd < 0) {
            data.columnMap = new HashMap<>();
            data.headerNames = new ArrayList<>();
            return data;
        }

        String headerLine = content.substring(0, headerEnd).trim();
        char delim = headerLine.contains(";") ? ';' : ',';

        // Parse header
        data.headerNames = parseCsvRecord(headerLine, delim);
        data.columnMap = mapColumns(data.headerNames);

        pos = headerEnd + 1;

        // Parse data records
        while (pos < content.length()) {
            if (content.charAt(pos) == '\n' || content.charAt(pos) == '\r') {
                pos++;
                continue;
            }

            List<String> fields = new ArrayList<>();
            while (true) {
                StringBuilder sb = new StringBuilder();
                if (pos < content.length() && content.charAt(pos) == '"') {
                    pos++;
                    while (pos < content.length()) {
                        char c = content.charAt(pos);
                        if (c == '"') {
                            if (pos + 1 < content.length() && content.charAt(pos + 1) == '"') {
                                sb.append('"');
                                pos += 2;
                            } else {
                                pos++;
                                break;
                            }
                        } else {
                            sb.append(c);
                            pos++;
                        }
                    }
                } else {
                    while (pos < content.length()) {
                        char c = content.charAt(pos);
                        if (c == delim || c == '\n' || c == '\r') break;
                        sb.append(c);
                        pos++;
                    }
                }
                fields.add(sb.toString());

                if (pos < content.length() && content.charAt(pos) == delim) {
                    pos++;
                } else {
                    if (pos < content.length() && content.charAt(pos) == '\r') pos++;
                    if (pos < content.length() && content.charAt(pos) == '\n') pos++;
                    break;
                }
            }

            data.rows.add(fields);
        }
        return data;
    }

    static List<String> parseCsvRecord(String line, char delim) {
        List<String> fields = new ArrayList<>();
        StringBuilder sb = new StringBuilder();
        boolean inQuotes = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (inQuotes) {
                if (c == '"') {
                    if (i + 1 < line.length() && line.charAt(i + 1) == '"') {
                        sb.append('"'); i++;
                    } else {
                        inQuotes = false;
                    }
                } else {
                    sb.append(c);
                }
            } else if (c == '"') {
                inQuotes = true;
            } else if (c == delim) {
                fields.add(sb.toString().trim());
                sb.setLength(0);
            } else {
                sb.append(c);
            }
        }
        fields.add(sb.toString().trim());
        return fields;
    }

    static Map<String, Integer> mapColumns(List<String> headers) {
        Map<String, Integer> map = new LinkedHashMap<>();
        for (int i = 0; i < headers.size(); i++) {
            String normalized = headers.get(i).toLowerCase()
                    .replaceAll("[^a-z0-9#]", ""); // strip special chars
            String canonical = COLUMN_ALIASES.get(normalized);
            if (canonical != null && !map.containsKey(canonical)) {
                map.put(canonical, i);
            }
        }
        return map;
    }
}
