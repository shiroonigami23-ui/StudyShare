const express = require('express');
const multer = require('multer');
const cors = require('cors');
const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// In-memory storage
let users = [];
let files = [];
let comments = [];
let votes = {};

// Admin password from frontend
const ADMIN_PASSWORD = "Shiro";

// Allowed file MIME types and max size for uploads
const allowedTypes = [
  'application/pdf',
  'application/epub+zip',
  'audio/mpeg',
  'image/jpeg',
  'image/jpg',
  'image/png'
];
const maxFileSize = 10 * 1024 * 1024; // 10 MB

// Multer storage and filter config for uploads
const storage = multer.memoryStorage();
const upload = multer({
  storage,
  limits: { fileSize: maxFileSize },
  fileFilter: (req, file, cb) => {
    cb(null, allowedTypes.includes(file.mimetype));
  }
});

// Helper to generate unique IDs
function genId() {
  return Math.random().toString(36).substr(2, 9);
}

// --- AUTH LOGIN ---
// Login endpoint
app.post('/login', (req, res) => {
  const { name, password, isAnonymous } = req.body;

  // If anonymous login requested, assign anon name
  if (isAnonymous) {
    const user = {
      id: genId(),
      name: `Anonymous_${genId()}`,
      isAdmin: false,
      isAnonymous: true
    };
    users.push(user);
    return res.json(user);
  }

  // Validate name provided
  if (!name) return res.status(400).json({ error: 'Name required' });

  // Check if admin login with correct password
  const isAdmin = (name.toLowerCase() === 'admin' && password === ADMIN_PASSWORD);

  const user = {
    id: genId(),
    name,
    isAdmin,
    isAnonymous: false
  };
  users.push(user);
  res.json(user);
});

// --- FILE UPLOAD ---
app.post('/upload', upload.single('file'), (req, res) => {
  const { uploaderId, uploaderName, isAnonymous } = req.body;

  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });

  if (!uploaderId || (!isAnonymous && !uploaderName)) {
    return res.status(400).json({ error: 'Uploader info required' });
  }

  // Save file metadata and buffer, initially not approved
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
// Admin authentication helper
function getAdminByIdAndPassword(id, password) {
  return users.find(u => u.id === id && u.isAdmin && password === ADMIN_PASSWORD);
}

// Approve file
app.post('/admin/approve', (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword)) {
    return res.status(403).json({ error: 'Admin only or wrong password' });
  }

  let file = files.find(f => f.id === fileId);
  if (!file) return res.status(404).json({ error: 'File not found' });

  file.isApproved = true;
  res.json({ success: true, file });
});

// Reject file
app.post('/admin/reject', (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword)) {
    return res.status(403).json({ error: 'Admin only or wrong password' });
  }

  files = files.filter(f => f.id !== fileId);
  res.json({ success: true });
});

// --- USER FILE ACTIONS ---
// Download file endpoint, only approved files or admins can download
app.get('/download/:fileId/:userId', (req, res) => {
  const { fileId, userId } = req.params;
  const user = users.find(u => u.id === userId);
  const file = files.find(f => f.id === fileId);

  if (!file) return res.status(404).json({ error: 'File not found' });
  if (!file.isApproved && (!user || !user.isAdmin)) {
    return res.status(403).json({ error: 'File not approved' });
  }

  res.setHeader('Content-Disposition', `attachment; filename="${file.originalName}"`);
  res.setHeader('Content-Type', file.mimeType);
  res.send(file.buffer);
});

// Upvote file endpoint
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

// Get all files, admins get all, users get only approved
app.get('/files/:userId', (req, res) => {
  let user = users.find(u => u.id === req.params.userId);
  let result = user && user.isAdmin ? files : files.filter(f => f.isApproved);
  res.json(result);
});

// --- COMMENTS ---
// Add comment endpoint
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

// Get all comments endpoint
app.get('/comments', (req, res) => {
  res.json(comments);
});

// --- ADMIN DASHBOARD ---
// Get admin stats
app.get('/admin/stats/:adminId/:adminPassword', (req, res) => {
  const { adminId, adminPassword } = req.params;
  if (!getAdminByIdAndPassword(adminId, adminPassword)) {
    return res.status(403).json({ error: 'Admin only or wrong password' });
  }

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
