const express = require('express');
const multer = require('multer');
const cors = require('cors');
const crypto = require('crypto');

const app = express();
const PORT = process.env.PORT || 10000;

const FRONTEND_URL = 'https://sharelit-1.onrender.com'; // your deployed frontend URL

// Middleware with CORS allowing your frontend domain
app.use(cors({
  origin: FRONTEND_URL,
  credentials: true,
}));
app.use(express.json());

const users = new Map(); // userId -> user object
const files = new Map(); // fileId -> file object
const comments = [];
const sessions = new Map(); // token -> user

const ADMIN_PASSWORD = 'Shiro';

const allowedFileTypes = [
  'application/pdf',
  'application/epub+zip',
  'audio/mpeg',
  'image/jpeg',
  'image/jpg',
  'image/png',
];

const MAX_FILE_SIZE = 10 * 1024 * 1024;

const storage = multer.memoryStorage();
const upload = multer({
  storage,
  limits: { fileSize: MAX_FILE_SIZE },
  fileFilter: (req, file, cb) => {
    cb(null, allowedFileTypes.includes(file.mimetype));
  },
});

function genId() {
  return crypto.randomBytes(8).toString('hex');
}
function genToken() {
  return crypto.randomBytes(16).toString('hex');
}

function authenticate(req, res, next) {
  const token = req.headers['authorization'];
  if (!token) return res.status(401).json({ error: 'No token provided' });
  const user = sessions.get(token);
  if (!user) return res.status(401).json({ error: 'Invalid token' });
  req.user = user;
  next();
}

function requireAdmin(req, res, next) {
  if (!req.user || !req.user.isAdmin) {
    return res.status(403).json({ error: 'Admin only' });
  }
  next();
}

// Login endpoint
app.post('/login', (req, res) => {
  const { name, password, isAnonymous } = req.body;
  if (isAnonymous) {
    const id = genId();
    const user = { id, name: `Anonymous_${id.slice(0, 5)}`, isAdmin: false, isAnonymous: true };
    users.set(id, user);
    const token = genToken();
    sessions.set(token, user);
    return res.json({ ...user, token });
  }

  if (!name) return res.status(400).json({ error: 'Name required' });

  const isAdmin = name.toLowerCase() === 'admin' && password === ADMIN_PASSWORD;
  if (name.toLowerCase() === 'admin' && !isAdmin) {
    return res.status(403).json({ error: 'Invalid admin password' });
  }

  const id = genId();
  const user = { id, name, isAdmin, isAnonymous: false };
  users.set(id, user);
  const token = genToken();
  sessions.set(token, user);

  return res.json({ ...user, token });
});

// File upload
app.post('/upload', authenticate, upload.single('file'), (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });

  const uploader = req.user;
  if (!uploader) return res.status(401).json({ error: 'Invalid user' });

  const fileId = genId();
  const file = {
    id: fileId,
    originalName: req.file.originalname,
    uploaderId: uploader.id,
    uploaderName: uploader.name,
    isApproved: uploader.isAdmin,
    status: uploader.isAdmin ? 'approved' : 'pending',
    mimeType: req.file.mimetype,
    fileSize: req.file.size,
    createdAt: new Date(),
    upvotes: 0,
  };
  files.set(fileId, file);

  res.json({ success: true, fileId });
});

// Comment submission
app.post('/comment', authenticate, (req, res) => {
  const { text } = req.body;
  if (!text) return res.status(400).json({ error: 'Comment text required' });

  const comment = {
    id: genId(),
    authorName: req.user.name,
    authorId: req.user.id,
    text,
    createdAt: new Date(),
  };
  comments.push(comment);
  res.json({ success: true, comment });
});

// Admin approve file
app.post('/admin/approve', authenticate, requireAdmin, (req, res) => {
  const { fileId } = req.body;
  const file = files.get(fileId);
  if (!file) return res.status(404).json({ error: 'File not found' });
  if (file.isApproved) return res.status(400).json({ error: 'File already approved' });

  file.isApproved = true;
  file.status = 'approved';
  file.approvedBy = req.user.name;
  file.approvedAt = new Date();

  res.json({ success: true });
});

// Admin reject file
app.post('/admin/reject', authenticate, requireAdmin, (req, res) => {
  const { fileId, reason } = req.body;
  const file = files.get(fileId);
  if (!file) return res.status(404).json({ error: 'File not found' });
  if (file.status === 'rejected') return res.status(400).json({ error: 'File already rejected' });

  file.status = 'rejected';
  file.rejectedBy = req.user.name;
  file.rejectedAt = new Date();
  file.rejectedReason = reason || 'No reason specified';

  res.json({ success: true });
});

// Admin delete file
app.post('/admin/delete', authenticate, requireAdmin, (req, res) => {
  const { fileId } = req.body;
  if (!files.has(fileId)) return res.status(404).json({ error: 'File not found' });

  files.delete(fileId);
  res.json({ success: true });
});

// User files list
app.get('/files/:userId', (req, res) => {
  const user = users.get(req.params.userId);
  if (!user) return res.status(404).json({ error: 'User not found' });

  const isAdmin = user.isAdmin;
  let resultFiles = Array.from(files.values());
  if (!isAdmin) resultFiles = resultFiles.filter((f) => f.isApproved);

  res.json(resultFiles);
});

// Get all comments
app.get('/comments', (req, res) => {
  res.json(comments);
});

// Upvote file
app.post('/upvote', authenticate, (req, res) => {
  const { fileId } = req.body;
  const file = files.get(fileId);
  if (!file) return res.status(404).json({ error: 'File not found' });

  file.upvotes = (file.upvotes || 0) + 1;
  res.json({ success: true, upvotes: file.upvotes });
});

// Download file (mocked)
app.get('/download/:fileId/:userId', (req, res) => {
  const { fileId, userId } = req.params;
  const user = users.get(userId);
  const file = files.get(fileId);
  if (!user) return res.status(404).json({ error: 'User not found' });
  if (!file || !file.isApproved) return res.status(404).json({ error: 'File not found or not approved' });

  res.setHeader('Content-Disposition', `attachment; filename="${file.originalName}"`);
  res.setHeader('Content-Type', file.mimeType);
  res.send(file.buffer || Buffer.from('Dummy file content'));
});

app.listen(PORT, () => console.log(`ShareLit backend running on port ${PORT}`));
