const express = require('express');
const multer = require('multer');
const cors = require('cors');
const app = express();
const PORT = 3000;

app.use(cors());
app.use(express.json());

// In-memory data storage
let users = [];
let files = [];
let comments = [];
let votes = {};

// File constraints for frontend
const allowedTypes = [
  'application/pdf',
  'application/epub+zip',
  'audio/mpeg',
  'image/jpeg',
  'image/jpg',
  'image/png'
];
const maxFileSize = 10 * 1024 * 1024; // 10 MB

// Multer config
const storage = multer.memoryStorage();
const upload = multer({
  storage,
  limits: { fileSize: maxFileSize },
  fileFilter: (req, file, cb) => {
    cb(null, allowedTypes.includes(file.mimetype));
  }
});

// Helper for unique IDs
function genId() {
  return Math.random().toString(36).substr(2, 9);
}

// --- AUTH ---
// Login endpoint (/login)
app.post('/login', (req, res) => {
  const { name, isAnonymous } = req.body;
  if (!name && !isAnonymous) return res.status(400).json({ error: 'Name or anonymous required' });
  let user = {
    id: genId(),
    name: isAnonymous ? `Anonymous_${genId()}` : name,
    isAdmin: name && name.toLowerCase() === 'admin',
    isAnonymous
  };
  users.push(user);
  res.json(user);
});

// --- FILE UPLOAD ---
// File upload (/upload)
app.post('/upload', upload.single('file'), (req, res) => {
  const { uploaderId, uploaderName, isAnonymous } = req.body;
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
  if (!uploaderId || (!isAnonymous && !uploaderName)) return res.status(400).json({ error: 'Uploader info required' });
  let f = {
    id: genId(),
    originalName: req.file.originalname,
    mimeType: req.file.mimetype,
    fileSize: req.file.size,
    uploaderId,
    uploaderName: isAnonymous ? `Anonymous_${genId()}` : uploaderName,
    isApproved: false,
    upvotes: 0,
    buffer: req.file.buffer,
    createdAt: new Date()
  };
  files.push(f);
  res.json({ success: true, file: f });
});

// --- ADMIN FILE ACTIONS ---
// Approve file (/admin/approve)
app.post('/admin/approve', (req, res) => {
  const { fileId, adminId } = req.body;
  let admin = users.find(u => u.id === adminId && u.isAdmin);
  if (!admin) return res.status(403).json({ error: 'Admin only' });
  let file = files.find(f => f.id === fileId);
  if (!file) return res.status(404).json({ error: 'File not found' });
  file.isApproved = true;
  res.json({ success: true, file });
});

// Reject file (/admin/reject)
app.post('/admin/reject', (req, res) => {
  const { fileId, adminId } = req.body;
  let admin = users.find(u => u.id === adminId && u.isAdmin);
  if (!admin) return res.status(403).json({ error: 'Admin only' });
  files = files.filter(f => f.id !== fileId);
  res.json({ success: true });
});

// --- USER FILE ACTIONS ---
// Download file (/download/:fileId/:userId)
app.get('/download/:fileId/:userId', (req, res) => {
  const { fileId, userId } = req.params;
  let user = users.find(u => u.id === userId);
  let file = files.find(f => f.id === fileId);
  if (!file) return res.status(404).json({ error: 'File not found' });
  if (!file.isApproved && !(user && user.isAdmin)) return res.status(403).json({ error: 'File not approved' });
  res.setHeader('Content-Disposition', `attachment; filename="${file.originalName}"`);
  res.setHeader('Content-Type', file.mimeType);
  res.send(file.buffer);
});

// Upvote file (/upvote)
app.post('/upvote', (req, res) => {
  const { fileId, userId } = req.body;
  if (!votes[userId]) votes[userId] = {};
  if (votes[userId][fileId]) return res.status(400).json({ error: 'Already voted' });
  let file = files.find(f => f.id === fileId && f.isApproved);
  if (!file) return res.status(404).json({ error: 'File not found or not approved' });
  file.upvotes++;
  votes[userId][fileId] = true;
  res.json({ success: true, upvotes: file.upvotes });
});

// Get files (/files/:userId)
app.get('/files/:userId', (req, res) => {
  let user = users.find(u => u.id === req.params.userId);
  let result = user && user.isAdmin ? files : files.filter(f => f.isApproved);
  res.json(result);
});

// --- COMMENTS ---
// Add comment (/comment)
app.post('/comment', (req, res) => {
  const { text, authorName, authorId } = req.body;
  if (!text || !authorName) return res.status(400).json({ error: 'Comment or name required' });
  let comment = {
    id: genId(),
    text,
    authorName,
    authorId: authorId || null,
    createdAt: new Date()
  };
  comments.push(comment);
  res.json({ success: true, comment });
});

// Get comments (/comments)
app.get('/comments', (req, res) => {
  res.json(comments);
});

// --- ADMIN DASHBOARD ---
// Get admin stats (/admin/stats/:adminId)
app.get('/admin/stats/:adminId', (req, res) => {
  let admin = users.find(u => u.id === req.params.adminId && u.isAdmin);
  if (!admin) return res.status(403).json({ error: 'Admin only' });
  let approved = files.filter(f => f.isApproved);
  let pending = files.filter(f => !f.isApproved);
  let totalUpvotes = files.reduce((total, f) => total + f.upvotes, 0);
  res.json({
    totalFiles: files.length,
    approved: approved.length,
    pending: pending.length,
    totalUpvotes
  });
});

app.listen(PORT, () => {
  console.log(`ShareLit backend running on port ${PORT}`);
});
