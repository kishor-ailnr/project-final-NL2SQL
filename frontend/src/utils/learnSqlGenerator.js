/**
 * Learn SQL Educational Content Generator
 * 
 * Dynamically breaks down actual queries, schemas, and execution results into
 * beginner-friendly educational explanations across 8 comprehensive sections
 * supporting English, Tamil, and Tanglish.
 */

// Detect query language (English, Tamil, or Tanglish)
export function detectLanguage(text = '', backendLang = '') {
  const str = String(text || '');
  // 1. Direct Tamil Unicode Range detection
  if (/[\u0B80-\u0BFF]/.test(str)) {
    return 'tamil';
  }
  // 2. Tanglish keywords and conversational particles
  const tanglishRegex = /\b(pannu|pannunga|kaatu|kaatunga|kudu|kudunga|irukku|irukkanga|sollinga|sollu|la|oda|entha|enga|yaaru|evvalavu|ethana|eduthu|kondi|ah|nu)\b/i;
  if (tanglishRegex.test(str)) {
    return 'tanglish';
  }
  // 3. Check backend detected language if explicitly provided
  if (backendLang && ['tamil', 'tanglish'].includes(backendLang.toLowerCase())) {
    return backendLang.toLowerCase();
  }
  return 'english';
}

// Extract primary SQL commands, clauses, tables, columns, and values
export function parseSqlDetails(rawSql = '') {
  if (!rawSql) {
    return {
      command: 'UNKNOWN',
      primaryTable: '',
      tables: [],
      columns: [],
      values: [],
      clauses: {},
      aggregates: [],
      hasWhere: false,
      hasJoin: false,
      hasGroupBy: false,
      hasOrderBy: false,
      hasLimit: false,
      statements: [],
    };
  }

  // Handle multi-statement queries (e.g. INSERT ...; SELECT ...;)
  const cleanStatements = rawSql
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean);

  const mainSql = cleanStatements[0] || rawSql.trim();
  const normalized = mainSql.replace(/\s+/g, ' ');

  // Command detection
  let command = 'SELECT';
  if (/^\s*INSERT\b/i.test(normalized)) command = 'INSERT';
  else if (/^\s*UPDATE\b/i.test(normalized)) command = 'UPDATE';
  else if (/^\s*DELETE\b/i.test(normalized)) command = 'DELETE';
  else if (/^\s*SELECT\b/i.test(normalized)) command = 'SELECT';

  // Table detection
  const tables = [];
  let primaryTable = '';

  const intoMatch = normalized.match(/INSERT\s+INTO\s+["`]?([a-zA-Z0-9_]+)["`]?/i);
  if (intoMatch) {
    primaryTable = intoMatch[1];
    tables.push(intoMatch[1]);
  }

  const updateMatch = normalized.match(/UPDATE\s+["`]?([a-zA-Z0-9_]+)["`]?/i);
  if (updateMatch) {
    primaryTable = updateMatch[1];
    tables.push(updateMatch[1]);
  }

  const fromMatch = normalized.match(/FROM\s+["`]?([a-zA-Z0-9_]+)["`]?/i);
  if (fromMatch && !primaryTable) {
    primaryTable = fromMatch[1];
    tables.push(fromMatch[1]);
  }

  // Join tables
  const joinMatches = normalized.matchAll(/(?:JOIN|INNER JOIN|LEFT JOIN|RIGHT JOIN)\s+["`]?([a-zA-Z0-9_]+)["`]?/gi);
  for (const m of joinMatches) {
    if (!tables.includes(m[1])) tables.push(m[1]);
  }

  // Columns & Values
  const columns = [];
  const values = [];

  if (command === 'INSERT') {
    const colMatch = normalized.match(/INSERT\s+INTO\s+["`]?\w+["`]?\s*\(([^)]+)\)/i);
    if (colMatch) {
      columns.push(
        ...colMatch[1]
          .split(',')
          .map((c) => c.replace(/["`']/g, '').trim())
          .filter(Boolean)
      );
    }
    const valMatch = normalized.match(/VALUES\s*\(([^)]+)\)/i);
    if (valMatch) {
      // Split preserving quoted strings
      const rawVals = valMatch[1].match(/(?:'[^']*'|"[^"]*"|[^,])+/g) || [];
      values.push(...rawVals.map((v) => v.trim().replace(/^['"]|['"]$/g, '')));
    }
  } else if (command === 'SELECT') {
    const selectMatch = normalized.match(/SELECT\s+(.*?)\s+FROM/i);
    if (selectMatch) {
      columns.push(
        ...selectMatch[1]
          .split(',')
          .map((c) => c.trim())
          .filter((c) => c && c !== '*')
      );
    }
  } else if (command === 'UPDATE') {
    const setMatch = normalized.match(/SET\s+(.*?)(?:\s+WHERE|$)/i);
    if (setMatch) {
      const assignments = setMatch[1].split(',');
      assignments.forEach((a) => {
        const parts = a.split('=');
        if (parts[0]) columns.push(parts[0].trim().replace(/["`']/g, ''));
        if (parts[1]) values.push(parts[1].trim().replace(/^['"]|['"]$/g, ''));
      });
    }
  }

  // WHERE Clause extraction
  let whereClause = '';
  const whereMatch = normalized.match(/WHERE\s+(.*?)(?:\s+GROUP\s+BY|\s+ORDER\s+BY|\s+LIMIT|$)/i);
  if (whereMatch) {
    whereClause = whereMatch[1].trim();
  }

  // Aggregates
  const aggregates = [];
  const aggMatches = normalized.matchAll(/\b(COUNT|SUM|AVG|MAX|MIN)\s*\([^)]*\)/gi);
  for (const a of aggMatches) {
    aggregates.push(a[0]);
  }

  return {
    command,
    primaryTable: primaryTable || 'table',
    tables: tables.length > 0 ? tables : [primaryTable || 'table'],
    columns,
    values,
    whereClause,
    aggregates,
    hasWhere: Boolean(whereClause),
    hasJoin: /JOIN\b/i.test(normalized),
    hasGroupBy: /GROUP\s+BY\b/i.test(normalized),
    hasOrderBy: /ORDER\s+BY\b/i.test(normalized),
    hasLimit: /LIMIT\s+\d+/i.test(normalized),
    statements: cleanStatements,
  };
}

/**
 * Generate all 8 Educational Sections
 */
export function generateLearnSqlContent({
  question = '',
  sql = '',
  explanation = '',
  result = [],
  rows_affected = null,
  error = null,
  isPendingWrite = false,
  notice = null,
  detectedLanguage = 'english',
}) {
  const lang = detectLanguage(question, detectedLanguage);
  const parsed = parseSqlDetails(sql);

  // -------------------------------------------------------------------------
  // SECTION 1: Your Question
  // -------------------------------------------------------------------------
  const section1 = {
    title: lang === 'tamil' ? 'உங்கள் கேள்வி' : lang === 'tanglish' ? 'Unga Question' : 'Your Question',
    content: question || (lang === 'tamil' ? 'கேள்வி விவரம் இல்லை' : 'No question provided'),
  };

  // -------------------------------------------------------------------------
  // SECTION 2: How the Question Was Understood
  // -------------------------------------------------------------------------
  let understoodSummary = '';
  let entityMappings = [];

  if (parsed.command === 'INSERT') {
    if (lang === 'tamil') {
      understoodSummary = `நீங்கள் '${parsed.primaryTable}' அட்டவணையில் ஒரு புதிய பதிவை (record) சேர்க்க விரும்பினீர்கள்.`;
    } else if (lang === 'tanglish') {
      understoodSummary = `Neenga '${parsed.primaryTable}' table la oru pudhu record add panna ketturukkinga.`;
    } else {
      understoodSummary = `You wanted to add a new record into the '${parsed.primaryTable}' table.`;
    }

    if (parsed.columns.length > 0 && parsed.values.length > 0) {
      entityMappings = parsed.columns.map((col, idx) => ({
        label: col.charAt(0).toUpperCase() + col.slice(1).replace(/_/g, ' '),
        column: col,
        value: parsed.values[idx] || (lang === 'tamil' ? 'கொடுக்கப்படவில்லை' : 'Not specified'),
      }));
    }
  } else if (parsed.command === 'UPDATE') {
    if (lang === 'tamil') {
      understoodSummary = `நீங்கள் '${parsed.primaryTable}' அட்டவணையில் உள்ள ஏற்கனவே இருக்கும் தரவை மாற்றியமைக்க (update) விரும்பினீர்கள்.`;
    } else if (lang === 'tanglish') {
      understoodSummary = `Neenga '${parsed.primaryTable}' table la irukkura data va modify/update panna ketturukkinga.`;
    } else {
      understoodSummary = `You wanted to update existing records in the '${parsed.primaryTable}' table.`;
    }

    if (parsed.columns.length > 0) {
      entityMappings = parsed.columns.map((col, idx) => ({
        label: col.charAt(0).toUpperCase() + col.slice(1).replace(/_/g, ' '),
        column: col,
        value: parsed.values[idx] || 'New Value',
      }));
    }
  } else if (parsed.command === 'DELETE') {
    if (lang === 'tamil') {
      understoodSummary = `நீங்கள் '${parsed.primaryTable}' அட்டவணையில் இருந்து குறிப்பிட்ட பதிவுகளை நீக்க விரும்பினீர்கள்.`;
    } else if (lang === 'tanglish') {
      understoodSummary = `Neenga '${parsed.primaryTable}' table la irunthu specific records ah delete panna ketturukkinga.`;
    } else {
      understoodSummary = `You wanted to delete matching records from the '${parsed.primaryTable}' table.`;
    }
  } else {
    // SELECT
    if (lang === 'tamil') {
      understoodSummary = `நீங்கள் '${parsed.primaryTable}' அட்டவணையில் இருந்து தகவல்களைத் தேடிப் பெற விரும்பினீர்கள்.`;
    } else if (lang === 'tanglish') {
      understoodSummary = `Neenga '${parsed.primaryTable}' table la irunthu information retrieve/paaka ketturukkinga.`;
    } else {
      understoodSummary = `You asked to retrieve information from the '${parsed.primaryTable}' table.`;
    }

    if (parsed.columns.length > 0) {
      entityMappings = parsed.columns.map((col) => ({
        label: col.replace(/_/g, ' '),
        column: col,
        value: lang === 'tamil' ? 'காண்பிக்கப்படும் நெடுவரிசை' : lang === 'tanglish' ? 'Display aagum column' : 'Requested column to view',
      }));
    }
  }

  const section2 = {
    title: lang === 'tamil' ? 'கேள்வி எவ்வாறு புரிந்துகொள்ளப்பட்டது' : lang === 'tanglish' ? 'Question epdi understand aachu' : 'How the Question Was Understood',
    summary: understoodSummary,
    mappings: entityMappings,
    targetTable: parsed.primaryTable,
    targetColumns: parsed.columns,
    mappingNote:
      lang === 'tamil'
        ? `கணினி இந்த மதிப்புகளை '${parsed.primaryTable}' அட்டவணையின் தொடர்புடைய நெடுவரிசைகளுடன் (columns) இணைத்துள்ளது.`
        : lang === 'tanglish'
        ? `System intha values ah '${parsed.primaryTable}' oda correct database columns ku map pannirukku.`
        : `The system mapped these values directly to the corresponding database columns in '${parsed.primaryTable}'.`,
  };

  // -------------------------------------------------------------------------
  // SECTION 3: Generated SQL
  // -------------------------------------------------------------------------
  const section3 = {
    title: lang === 'tamil' ? 'உருவாக்கப்பட்ட SQL வினவல்' : lang === 'tanglish' ? 'Generated SQL Query' : 'Generated SQL Query',
    sql: sql.trim(),
    statementsCount: parsed.statements.length,
  };

  // -------------------------------------------------------------------------
  // SECTION 4: SQL Command Explanation (Piece by piece)
  // -------------------------------------------------------------------------
  let commandWhat = '';
  let commandWhy = '';
  const pieceBreakdown = [];

  if (parsed.command === 'INSERT') {
    if (lang === 'tamil') {
      commandWhat = 'INSERT என்பது ஒரு தரவுத்தள அட்டவணையில் புதிய வரியை (record/row) சேர்க்கப் பயன்படும் SQL கட்டளையாகும்.';
      commandWhy = `உங்கள் கேள்வி '${parsed.primaryTable}' அட்டவணையில் புதிய விவரங்களைச் சேர்க்குமாறு கோரியதால், கணினி INSERT கட்டளையைப் பயன்படுத்தியது.`;
    } else if (lang === 'tanglish') {
      commandWhat = 'INSERT command database table la oru pudhu row/record ah add panna use aaguthu.';
      commandWhy = `Unga question la pudhu patient/record ah ADD panna sonnathala, system INSERT statement create pannuchu.`;
    } else {
      commandWhat = 'INSERT is an SQL command used to add a new record (row) into a database table.';
      commandWhy = `Your question asked the system to ADD new information. Since adding a new record requires inserting a row, an INSERT statement was generated.`;
    }

    pieceBreakdown.push({
      part: `INSERT INTO ${parsed.primaryTable}`,
      meaning:
        lang === 'tamil'
          ? `'${parsed.primaryTable}' அட்டவணையில் ஒரு புதிய பதிவு சேர்க்கப்பட வேண்டும் என்று தரவுத்தளத்திற்கு கூறுகிறது.`
          : lang === 'tanglish'
          ? `'${parsed.primaryTable}' table la pudhu record add aaganum nu database ku soluthu.`
          : `Tells the database that a new record should be added into the '${parsed.primaryTable}' table.`,
    });

    if (parsed.columns.length > 0) {
      pieceBreakdown.push({
        part: `(${parsed.columns.join(', ')})`,
        meaning:
          lang === 'tamil'
            ? 'மதிப்புகள் சேமிக்கப்பட வேண்டிய குறிப்பிட்ட நெடுவரிசைகளின் பெயர்கள்.'
            : lang === 'tanglish'
            ? 'Values store aaga vendiya database column names.'
            : 'Specifies the exact columns where the new values will be stored.',
      });
    }

    if (parsed.values.length > 0) {
      pieceBreakdown.push({
        part: 'VALUES',
        meaning:
          lang === 'tamil'
            ? 'நெடுவரிசைகளில் செருகப்பட வேண்டிய உண்மையான மதிப்புகளைக் குறிப்பிடுகிறது.'
            : lang === 'tanglish'
            ? 'Columns la poda vendiya actual values ah specify pannuthu.'
            : 'Keyword introducing the actual data values to be inserted.',
      });

      pieceBreakdown.push({
        part: `(${parsed.values.map((v) => `'${v}'`).join(', ')})`,
        meaning:
          lang === 'tamil'
            ? 'உங்கள் கேள்வியிலிருந்து எடுக்கப்பட்ட உண்மையான மதிப்புகள்.'
            : lang === 'tanglish'
            ? 'Unga natural language question la irunthu edukkapatta actual values.'
            : 'The specific values extracted from your question, placed in matching column order.',
      });
    }
  } else if (parsed.command === 'UPDATE') {
    if (lang === 'tamil') {
      commandWhat = 'UPDATE என்பது அட்டவணையில் ஏற்கனவே இருக்கும் பதிவுகளில் உள்ள மதிப்புகளை மாற்றியமைக்கப் பயன்படும் கட்டளையாகும்.';
      commandWhy = 'ஏற்கனவே இருக்கும் பதிவை மாற்றியமைக்கக் கோரியதால் UPDATE பயன்படுத்தப்பட்டது.';
    } else if (lang === 'tanglish') {
      commandWhat = 'UPDATE command already irukkura records oda values ah modify panna use aaguthu.';
      commandWhy = 'Existing record ah update panna sonnathala UPDATE generate aachu.';
    } else {
      commandWhat = 'UPDATE is an SQL command used to modify existing records in a database table.';
      commandWhy = 'Your question asked to edit or update an existing record.';
    }

    pieceBreakdown.push({
      part: `UPDATE ${parsed.primaryTable}`,
      meaning:
        lang === 'tamil'
          ? `'${parsed.primaryTable}' அட்டவணையை மாற்றியமைக்கத் தேர்ந்தெடுக்கிறது.`
          : lang === 'tanglish'
          ? `'${parsed.primaryTable}' table ah target pannuthu.`
          : `Specifies '${parsed.primaryTable}' as the table to update.`,
    });

    pieceBreakdown.push({
      part: 'SET ...',
      meaning:
        lang === 'tamil'
          ? 'புதிய மதிப்புகளை ஒதுக்குகிறது.'
          : lang === 'tanglish'
          ? 'Pudhu values assign pannuthu.'
          : 'Assigns the new values to the specified columns.',
    });
  } else if (parsed.command === 'DELETE') {
    if (lang === 'tamil') {
      commandWhat = 'DELETE என்பது அட்டவணையில் இருந்து பதிவுகளை நீக்கப் பயன்படும் கட்டளையாகும்.';
      commandWhy = 'பதிவை நீக்குமாறு கேட்டதால் DELETE பயன்படுத்தப்பட்டது.';
    } else if (lang === 'tanglish') {
      commandWhat = 'DELETE command database table la irunthu records ah remove panna use aaguthu.';
      commandWhy = 'Record ah delete panna sonnathala DELETE statement use pannirukku.';
    } else {
      commandWhat = 'DELETE is an SQL command used to remove records from a database table.';
      commandWhy = 'Your request asked to remove records matching your condition.';
    }

    pieceBreakdown.push({
      part: `DELETE FROM ${parsed.primaryTable}`,
      meaning:
        lang === 'tamil'
          ? `'${parsed.primaryTable}' அட்டவணையில் இருந்து நீக்கத் தொடங்குகிறது.`
          : lang === 'tanglish'
          ? `'${parsed.primaryTable}' table la irunthu records remove panna aarambikithu.`
          : `Specifies that rows should be deleted from '${parsed.primaryTable}'.`,
    });
  } else {
    // SELECT
    if (lang === 'tamil') {
      commandWhat = 'SELECT என்பது தரவுத்தளத்தில் இருந்து தேவையான தகவல்களை மீட்டெடுக்கப் பயன்படும் முக்கிய கட்டளையாகும்.';
      commandWhy = `நீங்கள் கேட்ட கேள்விக்கான பதிலைப் பெற '${parsed.primaryTable}' அட்டவணையில் இருந்து தரவை வாசிக்க SELECT பயன்படுத்தப்பட்டது.`;
    } else if (lang === 'tanglish') {
      commandWhat = 'SELECT command database la irunthu data va fetch/retrieve panna use aagum most fundamental command.';
      commandWhy = `Unga question ku answer kandupidikka '${parsed.primaryTable}' table la irunthu data va read panna SELECT use aachu.`;
    } else {
      commandWhat = 'SELECT is the fundamental SQL command used to query and fetch records from a database.';
      commandWhy = `Your question asked to view or find information, so a SELECT query was generated to retrieve the matching rows from '${parsed.primaryTable}'.`;
    }

    pieceBreakdown.push({
      part: parsed.columns.length > 0 ? `SELECT ${parsed.columns.join(', ')}` : 'SELECT *',
      meaning:
        lang === 'tamil'
          ? parsed.columns.length > 0
            ? 'தேர்ந்தெடுக்கப்பட்ட குறிப்பிட்ட நெடுவரிசைகளை மட்டும் காண்பிக்கக் கூறுகிறது.'
            : 'அனைத்து நெடுவரிசைகளின் விவரங்களையும் மீட்டெடுக்கிறது.'
          : lang === 'tanglish'
          ? parsed.columns.length > 0
            ? 'Specific columns ah mattum retrieve panni kaatuthu.'
            : 'Ellaa columns oda values ayum fetch pannuthu.'
          : parsed.columns.length > 0
          ? 'Instructs the database to retrieve only these specific columns.'
          : 'Retrieves all available columns from the table (* means all columns).',
    });

    pieceBreakdown.push({
      part: `FROM ${parsed.primaryTable}`,
      meaning:
        lang === 'tamil'
          ? `தரவு எந்த அட்டவணையில் இருந்து எடுக்கப்பட வேண்டும் என்பதைக் குறிப்பிடுகிறது ('${parsed.primaryTable}').`
          : lang === 'tanglish'
          ? `Data entha table la irunthu varanum nu solluthu ('${parsed.primaryTable}').`
          : `Identifies the source table ('${parsed.primaryTable}') from which to pull data.`,
    });
  }

  // Add WHERE explanation if present
  if (parsed.hasWhere) {
    pieceBreakdown.push({
      part: `WHERE ${parsed.whereClause}`,
      meaning:
        lang === 'tamil'
          ? 'நிபந்தனை வடிகட்டி: குறிப்பிட்ட நிபந்தனையைப் பூர்த்தி செய்யும் வரிகளை மட்டுமே தேர்ந்தெடுக்கிறது.'
          : lang === 'tanglish'
          ? 'Filter condition: Intha condition match aagura rows ah mattum filter pannuthu.'
          : `Filtering clause: Restricts the operation to only rows that satisfy '${parsed.whereClause}'.`,
    });
  }

  // Add JOIN explanation if present
  if (parsed.hasJoin) {
    pieceBreakdown.push({
      part: 'JOIN ... ON ...',
      meaning:
        lang === 'tamil'
          ? 'தொடர்புடைய பொதுவான நெடுவரிசையின் அடிப்படையில் இரண்டு அட்டவணைகளை இணைக்கிறது.'
          : lang === 'tanglish'
          ? 'Rendu related tables ah matching column moolama connect pannuthu.'
          : 'Combines rows from two or more tables based on a related column between them.',
    });
  }

  // Add GROUP BY / Aggregates
  if (parsed.hasGroupBy) {
    pieceBreakdown.push({
      part: 'GROUP BY ...',
      meaning:
        lang === 'tamil'
          ? 'ஒரே மாதிரியான மதிப்புகளைக் கொண்ட வரிகளை குழுக்களாகத் தொகுக்கிறது (aggregation).'
          : lang === 'tanglish'
          ? 'Same values irukkura rows ah group panni aggregate summary poduthu.'
          : 'Groups rows that have the same values into summary rows (e.g. for count/sum).',
    });
  }

  // Add ORDER BY
  if (parsed.hasOrderBy) {
    pieceBreakdown.push({
      part: 'ORDER BY ...',
      meaning:
        lang === 'tamil'
          ? 'முடிவுகளை ஏறுவரிசை அல்லது இறங்குவரிசையில் வரிசைப்படுத்துகிறது.'
          : lang === 'tanglish'
          ? 'Results ah ascending or descending order la sort pannuthu.'
          : 'Sorts the final results in ascending (ASC) or descending (DESC) order.',
    });
  }

  // Add Multi-statement chained query explanation (e.g. INSERT + SELECT)
  if (parsed.statements.length > 1) {
    pieceBreakdown.push({
      part: parsed.statements[1],
      meaning:
        lang === 'tamil'
          ? 'செருகப்பட்ட புதிய மாற்றங்களுக்குப் பிறகு அட்டவணையின் தற்போதைய முழு நிலையை மீட்டெடுத்துக் காண்பிக்கிறது.'
          : lang === 'tanglish'
          ? 'Insert panna aprom updated full table ah screen la kaata intha second SELECT query run aaguthu.'
          : 'Chained query: Immediately retrieves the full table after the insertion to display the updated state.',
    });
  }

  const section4 = {
    title: lang === 'tamil' ? 'SQL கட்டளை விளக்கம்' : lang === 'tanglish' ? 'SQL Command Explanation' : 'SQL Command Explanation',
    command: parsed.command,
    whatIs: commandWhat,
    whyUsed: commandWhy,
    pieces: pieceBreakdown,
  };

  // -------------------------------------------------------------------------
  // SECTION 5: Question → SQL Conversion (Visual Flow)
  // -------------------------------------------------------------------------
  const flowSteps = [
    {
      step: 1,
      name: lang === 'tamil' ? 'பயனர் கேள்வி' : lang === 'tanglish' ? 'User Question' : 'User Question',
      detail: `"${question}"`,
      badge: 'Input',
    },
    {
      step: 2,
      name: lang === 'tamil' ? 'இயற்கை மொழி செயலாக்கம்' : lang === 'tanglish' ? 'Natural Language Processing' : 'Natural Language Processing',
      detail:
        lang === 'tamil'
          ? `நோக்கம் கண்டறியப்பட்டது: ${parsed.command}`
          : lang === 'tanglish'
          ? `Intent detect aachu: ${parsed.command}`
          : `Intent Detected: ${parsed.command} Operation`,
      badge: 'NLP Layer',
    },
    {
      step: 3,
      name: lang === 'tamil' ? 'அட்டவணை அடையாளம் காணப்பட்டது' : lang === 'tanglish' ? 'Table Identified' : 'Table Identified',
      detail: parsed.primaryTable,
      badge: 'Schema Mapping',
    },
    {
      step: 4,
      name: lang === 'tamil' ? 'நெடுவரிசைகள் அடையாளம் காணப்பட்டன' : lang === 'tanglish' ? 'Columns Identified' : 'Columns Identified',
      detail: parsed.columns.length > 0 ? parsed.columns.join(', ') : 'All Columns (*)',
      badge: 'Mapping',
    },
    {
      step: 5,
      name: lang === 'tamil' ? 'மதிப்புகள் / நிபந்தனைகள் பிரித்தெடுக்கப்பட்டன' : lang === 'tanglish' ? 'Values / Conditions Extracted' : 'Values / Conditions Extracted',
      detail:
        parsed.values.length > 0
          ? parsed.values.join(', ')
          : parsed.hasWhere
          ? parsed.whereClause
          : (lang === 'tamil' ? 'அனைத்து பதிவுகள்' : 'All Rows'),
      badge: 'Extraction',
    },
    {
      step: 6,
      name: lang === 'tamil' ? 'SQL வினவல் உருவாக்கப்பட்டது' : lang === 'tanglish' ? 'SQL Generated' : 'SQL Generated',
      detail: `${parsed.command} INTO/FROM ${parsed.primaryTable} ...`,
      badge: 'AI Generation',
    },
    {
      step: 7,
      name: lang === 'tamil' ? 'SQL சரிபார்க்கப்பட்டது (Validation)' : lang === 'tanglish' ? 'SQL Validated' : 'SQL Validated',
      detail: lang === 'tamil' ? 'தவறுகள் ஏதுமின்றி தொடரியல் (Syntax) சரிபார்க்கப்பட்டது' : 'Syntax & safety verified via sqlglot',
      badge: 'Safety Check',
    },
    {
      step: 8,
      name: lang === 'tamil' ? 'தரவுத்தளத்தில் செயல்படுத்தப்பட்டது' : lang === 'tanglish' ? 'Database la Executed' : 'Executed against Database',
      detail: isPendingWrite
        ? (lang === 'tamil' ? 'பயனர் ஒப்புதலுக்காக காத்திருக்கிறது' : 'Staged for write confirmation')
        : (lang === 'tamil' ? 'வெற்றிகரமாக இயக்கப்பட்டது' : 'Executed in SQLite engine'),
      badge: 'Database',
    },
  ];

  const section5 = {
    title: lang === 'tamil' ? 'கேள்வி → SQL மாற்றப் படிநிலைகள்' : lang === 'tanglish' ? 'Question → SQL Conversion Flow' : 'Question → SQL Conversion Flow',
    steps: flowSteps,
  };

  // -------------------------------------------------------------------------
  // SECTION 6: What Happened When SQL Was Executed?
  // -------------------------------------------------------------------------
  let execHeadline = '';
  let execDetails = '';
  let execStatusType = 'success'; // 'success' | 'warning' | 'error' | 'pending'

  if (error) {
    execStatusType = 'error';
    execHeadline = lang === 'tamil' ? 'SQL செயலாக்கம் தோல்வியடைந்தது.' : lang === 'tanglish' ? 'SQL execution fail aachu.' : 'SQL execution failed.';
    execDetails = `${lang === 'tamil' ? 'பிழை விவரம்' : 'Error details'}: ${error}\n${lang === 'tamil' ? 'சரிசெய்ய என்ன செய்யலாம்: அட்டவணை மற்றும் நெடுவரிசை பெயர்களை மீண்டும் சரிபார்க்கவும்.' : 'Suggested action: Verify that table names and column names match the schema.'}`;
  } else if (notice) {
    execStatusType = 'warning';
    execHeadline = lang === 'tamil' ? 'நகல் பதிவு கண்டறியப்பட்டது (Duplicate Record)' : lang === 'tanglish' ? 'Duplicate record detect aachu' : 'Duplicate Record Notice';
    execDetails = notice;
  } else if (isPendingWrite) {
    execStatusType = 'pending';
    execHeadline = lang === 'tamil' ? 'எழுதும் செயல்பாடு (Pending Confirmation)' : lang === 'tanglish' ? 'Write Operation Pending' : 'Write Operation Staged for Confirmation';
    execDetails =
      lang === 'tamil'
        ? 'வினவல் உருவாக்கப்பட்டு சரிபார்க்கப்பட்டது. உங்கள் தரவுத்தளத்தின் பாதுகாப்பிற்காக உங்கள் உறுதிப்படுத்தலுக்குப் பிறகு செயல்படுத்தப்படும்.'
        : lang === 'tanglish'
        ? 'SQL generate aagi ready ah irukku. Unga database safe ah irukka unga confirmation ku wait pannuthu.'
        : 'The query was generated and validated. For database safety, write operations require your confirmation before modifying data.';
  } else if (parsed.command === 'INSERT') {
    execStatusType = 'success';
    const aff = rows_affected !== null ? rows_affected : 1;
    execHeadline =
      lang === 'tamil'
        ? `தரவுத்தளம் INSERT கட்டளையைச் செயல்படுத்தி ${aff} புதிய வரியைச் சேர்த்தது.`
        : lang === 'tanglish'
        ? `Database INSERT command run panni ${aff} pudhu row ah table la add pannirukku.`
        : `The database processed the INSERT command and added ${aff} new row to '${parsed.primaryTable}'.`;
    execDetails = `${lang === 'tamil' ? 'பாதிக்கப்பட்ட வரிகள்' : 'Affected rows'}: ${aff}`;
  } else if (parsed.command === 'UPDATE') {
    execStatusType = 'success';
    const aff = rows_affected !== null ? rows_affected : 1;
    execHeadline =
      lang === 'tamil'
        ? `தரவுத்தளம் ${aff} வரிகளில் மதிப்புகளை மாற்றியமைத்தது.`
        : lang === 'tanglish'
        ? `Database ${aff} rows ah successfully update pannirukku.`
        : `The database processed the UPDATE command and modified ${aff} row(s).`;
    execDetails = `${lang === 'tamil' ? 'பாதிக்கப்பட்ட வரிகள்' : 'Affected rows'}: ${aff}`;
  } else if (parsed.command === 'DELETE') {
    execStatusType = 'success';
    const aff = rows_affected !== null ? rows_affected : 1;
    execHeadline =
      lang === 'tamil'
        ? `தரவுத்தளம் ${aff} வரிகளை நீக்கியது.`
        : lang === 'tanglish'
        ? `Database ${aff} rows ah delete pannirukku.`
        : `The database processed the DELETE command and deleted ${aff} row(s).`;
    execDetails = `${lang === 'tamil' ? 'நீக்கப்பட்ட வரிகள்' : 'Deleted rows'}: ${aff}`;
  } else {
    // SELECT
    execStatusType = 'success';
    const count = Array.isArray(result) ? result.length : 0;
    execHeadline =
      lang === 'tamil'
        ? `தரவுத்தளம் ${count} பொருந்தக்கூடிய பதிவுகளை மீட்டெடுத்து வழங்கியது.`
        : lang === 'tanglish'
        ? `Database ${count} matching records ah retrieve panni tharuthu.`
        : `The database executed the query and returned ${count} matching record(s).`;
    execDetails = `${lang === 'tamil' ? 'மீட்டெடுக்கப்பட்ட பதிவுகளின் எண்ணிக்கை' : 'Returned records'}: ${count}`;
  }

  const section6 = {
    title: lang === 'tamil' ? 'SQL இயக்கப்பட்டபோது என்ன நடந்தது?' : lang === 'tanglish' ? 'SQL run aana aprom enna aachu?' : 'What Happened When SQL Was Executed?',
    statusType: execStatusType,
    headline: execHeadline,
    details: execDetails,
  };

  // -------------------------------------------------------------------------
  // SECTION 7: Final Result
  // -------------------------------------------------------------------------
  let finalResultText = '';
  if (error) {
    finalResultText = lang === 'tamil' ? 'செயல்பாடு நிறைவடையவில்லை.' : 'Operation could not complete.';
  } else if (notice) {
    finalResultText =
      lang === 'tamil'
        ? 'ஏற்கனவே உள்ள தரவு அப்படியே உள்ளது, புதிய நகல் வரி சேர்க்கப்படவில்லை.'
        : lang === 'tanglish'
        ? 'Already irukkura data intact ah irukku, duplicate row add aagala.'
        : 'Existing data was preserved. No duplicate row was added to the database.';
  } else if (isPendingWrite) {
    finalResultText =
      lang === 'tamil'
        ? 'உறுதிசெய்தவுடன் தரவுத்தளத்தில் சேர்க்கப்படும்.'
        : lang === 'tanglish'
        ? 'Confirm panna odane table la add aagidum.'
        : 'Ready to be executed upon your confirmation.';
  } else if (parsed.command === 'INSERT') {
    finalResultText =
      lang === 'tamil'
        ? `'${parsed.primaryTable}' அட்டவணையில் ஒரு புதிய பதிவு வெற்றிகரமாக சேர்க்கப்பட்டது.`
        : lang === 'tanglish'
        ? `'${parsed.primaryTable}' table la oru pudhu record successfully add aagirukku.`
        : `A new record was successfully added to the '${parsed.primaryTable}' table.`;
  } else if (parsed.command === 'UPDATE') {
    finalResultText =
      lang === 'tamil'
        ? `'${parsed.primaryTable}' அட்டவணையில் உள்ள விவரங்கள் வெற்றிகரமாக புதுப்பிக்கப்பட்டன.`
        : lang === 'tanglish'
        ? `'${parsed.primaryTable}' table records successfully update aagirukku.`
        : `Matching records in '${parsed.primaryTable}' were successfully updated.`;
  } else if (parsed.command === 'DELETE') {
    finalResultText =
      lang === 'tamil'
        ? `குறிப்பிட்ட பதிவுகள் வெற்றிகரமாக நீக்கப்பட்டன.`
        : lang === 'tanglish'
        ? `Selected records successfully delete aagirukku.`
        : `Matching records were successfully removed from '${parsed.primaryTable}'.`;
  } else {
    const count = Array.isArray(result) ? result.length : 0;
    finalResultText =
      lang === 'tamil'
        ? `தரவுத்தளம் உங்கள் வினவலுக்குரிய ${count} பதிவுகளைக் காண்பிக்கிறது.`
        : lang === 'tanglish'
        ? `Database unga query ku ${count} records ah fetch panni kaatuthu.`
        : `The database returned ${count} matching records for your query.`;
  }

  const section7 = {
    title: lang === 'tamil' ? 'இறுதி முடிவு' : lang === 'tanglish' ? 'Final Result' : 'Final Result',
    result: finalResultText,
  };

  // -------------------------------------------------------------------------
  // SECTION 8: Complete Learning Summary & "What you learned"
  // -------------------------------------------------------------------------
  const learnedPoints = [];

  if (parsed.command === 'INSERT') {
    if (lang === 'tamil') {
      learnedPoints.push('INSERT: அட்டவணையில் ஒரு புதிய வரியை சேர்க்கப் பயன்படுகிறது.');
      learnedPoints.push(`INTO ${parsed.primaryTable}: புதிய தரவைச் சேர்க்க வேண்டிய இலக்கு அட்டவணையைக் குறிக்கிறது.`);
      learnedPoints.push('Columns (நெடுவரிசைகள்): மதிப்புகள் எங்கு சேமிக்கப்பட வேண்டும் என்பதை வரிசையாகக் குறிப்பிடுகிறது.');
      learnedPoints.push('VALUES: செருகப்பட வேண்டிய குறிப்பிட்ட தரவு மதிப்புகளை வழங்குகிறது.');
    } else if (lang === 'tanglish') {
      learnedPoints.push('INSERT: Table la pudhu row/record add panna use aagum.');
      learnedPoints.push(`INTO ${parsed.primaryTable}: Target table ah select pannuthu.`);
      learnedPoints.push('Columns: Values entha columns la store aaganum nu specify pannuthu.');
      learnedPoints.push('VALUES: Insert panna vendiya data values ah provide pannuthu.');
    } else {
      learnedPoints.push('INSERT is used to add a new row to a database table.');
      learnedPoints.push(`INTO specifies the target table ('${parsed.primaryTable}').`);
      learnedPoints.push('Column names define where each value will be stored.');
      learnedPoints.push('VALUES provides the actual data values to insert in matching order.');
    }
  } else if (parsed.command === 'UPDATE') {
    if (lang === 'tamil') {
      learnedPoints.push('UPDATE: ஏற்கனவே இருக்கும் பதிவுகளை மாற்றியமைக்கப் பயன்படுகிறது.');
      learnedPoints.push('SET: நெடுவரிசைகளுக்கு புதிய மதிப்புகளை ஒதுக்குகிறது.');
      if (parsed.hasWhere) learnedPoints.push('WHERE: அனைத்து வரிகளையும் மாற்றாமல் குறிப்பிட்ட வரியை மட்டும் மாற்றுகிறது.');
    } else {
      learnedPoints.push('UPDATE modifies existing records in a table.');
      learnedPoints.push('SET assigns new values to specific columns.');
      if (parsed.hasWhere) learnedPoints.push('WHERE ensures only target rows are updated, preventing accidental updates to the whole table.');
    }
  } else if (parsed.command === 'DELETE') {
    if (lang === 'tamil') {
      learnedPoints.push('DELETE FROM: அட்டவணையில் இருந்து வரிகளை நீக்கப் பயன்படுகிறது.');
      learnedPoints.push('WHERE: நீக்கப்பட வேண்டிய குறிப்பிட்ட வரியை மட்டும் அடையாளம் காட்டுகிறது.');
    } else {
      learnedPoints.push('DELETE FROM removes rows from a database table.');
      learnedPoints.push('WHERE clause specifies which rows to delete; without WHERE, all rows would be deleted.');
    }
  } else {
    // SELECT
    if (lang === 'tamil') {
      learnedPoints.push('SELECT: தரவுத்தளத்தில் இருந்து குறிப்பிட்ட நெடுவரிசைகளை வாசிக்கப் பயன்படுகிறது.');
      learnedPoints.push(`FROM ${parsed.primaryTable}: தரவு எந்த அட்டவணையில் இருந்து எடுக்கப்படுகிறது என்பதைத் தெரிவிக்கிறது.`);
      if (parsed.hasWhere) learnedPoints.push('WHERE: நிபந்தனைகளின் அடிப்படையில் வரிகளை வடிகட்டுகிறது.');
      if (parsed.hasOrderBy) learnedPoints.push('ORDER BY: முடிவுகளை வரிசைப்படுத்துகிறது.');
      if (parsed.hasGroupBy) learnedPoints.push('GROUP BY: பொதுவான மதிப்புகளின்படி தொகுக்கிறது.');
    } else if (lang === 'tanglish') {
      learnedPoints.push('SELECT: Table la irunthu data fetch panna use aagum.');
      learnedPoints.push(`FROM ${parsed.primaryTable}: Source table ah specify pannuthu.`);
      if (parsed.hasWhere) learnedPoints.push('WHERE: Specific conditions vechu rows ah filter pannuthu.');
      if (parsed.hasOrderBy) learnedPoints.push('ORDER BY: Results ah sort panni kaatuthu.');
    } else {
      learnedPoints.push('SELECT specifies which columns to retrieve from the database.');
      learnedPoints.push(`FROM identifies the source table ('${parsed.primaryTable}').`);
      if (parsed.hasWhere) learnedPoints.push('WHERE filters records so only rows meeting the criteria are returned.');
      if (parsed.hasOrderBy) learnedPoints.push('ORDER BY sorts the returned records by specific columns.');
      if (parsed.hasGroupBy) learnedPoints.push('GROUP BY groups matching rows for summary calculations.');
    }
  }

  const section8 = {
    title: lang === 'tamil' ? 'முழுமையான கற்றல் சுருக்கம்' : lang === 'tanglish' ? 'Complete Learning Summary' : 'Complete Learning Summary',
    learnedTitle: lang === 'tamil' ? 'நீங்கள் கற்றுக்கொண்டவை:' : lang === 'tanglish' ? 'Neenga enna kathukitteenga:' : 'What you learned:',
    learnedPoints,
  };

  return {
    lang,
    section1,
    section2,
    section3,
    section4,
    section5,
    section6,
    section7,
    section8,
  };
}
