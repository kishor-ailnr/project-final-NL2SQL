import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Helper for clean error formatting
const formatError = (error, fallbackMessage) => {
  if (error.response?.data?.detail) {
    const detail = error.response.data.detail;
    if (typeof detail === 'string') return new Error(detail);
    if (Array.isArray(detail)) {
      return new Error(detail.map((e) => e.msg || JSON.stringify(e)).join(', '));
    }
  }
  if (error.response?.data?.message) {
    return new Error(error.response.data.message);
  }
  if (error.message === 'Network Error' || error.code === 'ERR_NETWORK') {
    return new Error('Unable to connect to backend server at ' + BASE_URL + '. Please check server status.');
  }
  return new Error(error.message || fallbackMessage);
};

export async function connectDB({ db_type, connection_string, demo_name }) {
  try {
    const response = await api.post('/api/connect-db', {
      db_type,
      connection_string,
      demo_name,
    });
    return response.data; // { session_id, status, tables }
  } catch (err) {
    throw formatError(err, 'Failed to connect to database.');
  }
}

export async function sendQuery({ session_id, conversation_id, text, language = 'auto' }) {
  try {
    const response = await api.post('/api/query', {
      session_id,
      conversation_id,
      text,
      language,
    });
    return response.data; // { query_id, sql, explanation, confidence, needs_clarification, clarification_question, query_type, result, chart_type, interpreted_text }
  } catch (err) {
    throw formatError(err, 'Failed to process query.');
  }
}

export async function createConversation(session_id) {
  try {
    const response = await api.post('/api/conversations/new', {
      session_id,
    });
    return response.data; // { conversation_id, created_at }
  } catch (err) {
    throw formatError(err, 'Failed to create new conversation.');
  }
}

export async function getConversations(session_id) {
  try {
    const response = await api.get('/api/conversations', {
      params: { session_id },
    });
    return response.data; // { conversations: [{ conversation_id, title, created_at }] }
  } catch (err) {
    throw formatError(err, 'Failed to fetch conversations.');
  }
}

export async function getConversationMessages(conversation_id) {
  try {
    const response = await api.get(`/api/conversations/${conversation_id}/messages`);
    return response.data; // { messages: [{ nl_query, sql, explanation, result, chart_type, timestamp }] }
  } catch (err) {
    throw formatError(err, 'Failed to load conversation messages.');
  }
}

export async function confirmWrite({ session_id, query_id, confirmed }) {
  try {
    const response = await api.post('/api/confirm-write', {
      session_id,
      query_id,
      confirmed,
    });
    return response.data; // { status, rows_affected }
  } catch (err) {
    throw formatError(err, 'Failed to process write confirmation.');
  }
}

export async function sendVoice(audioBlob) {
  try {
    const formData = new FormData();
    formData.append('file', audioBlob, 'audio.webm');

    const response = await api.post('/api/voice', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data; // { transcript, detected_language }
  } catch (err) {
    throw formatError(err, 'Failed to transcribe voice input.');
  }
}

export async function getHistory(session_id) {
  try {
    const response = await api.get('/api/history', {
      params: { session_id },
    });
    return response.data; // { conversations: [{ id, nl_query, timestamp }] }
  } catch (err) {
    throw formatError(err, 'Failed to fetch query history.');
  }
}

export async function uploadDB(file) {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post('/api/upload-db', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data; // { session_id, status, tables }
  } catch (err) {
    throw formatError(err, 'Failed to upload and parse database file.');
  }
}

