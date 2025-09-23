const express = require('express');
const multer = require('multer');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 10000;

// Middleware
app.use(cors());
app.use(express.json());

// Persistent storage setup
const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir);

const usersFile = path.join(dataDir, 'users.json');
const commentsFile = path.join(dataDir, 'comments.json');
const votesFile = path.join(dataDir, 'votes.json');
const uploadsDir = path.join(dataDir, 'uploads');

if (!fs.existsSync(uploadsDir)) fs.mkdirSync(uploadsDir);

// Load/save helpers
function loadData(filePath) {
  if (fs.existsSync(filePath)) {
    try {
      return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    } catch {
      return [];
    }
  } else return [];
}

function saveData(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
}

// Load existing data
let users = loadData(usersFile);
let comments = loadData(commentsFile);
let votes = loadData(votesFile);

const ADMINPASSWORD = 'Shiro';

// Allowed file types & size limit
const allowedTypes = [
  'application/pdf',
  'application/epub+zip',
  'audio/mpeg',
  'image/jpeg',
  'image/jpg',
  'image/png',
];
const maxFileSize = 10 * 1024 * 1024;

// Multer disk storage for real file saving
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, uploadsDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, uniqueSuffix + '-' + file.originalname);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: maxFileSize },
  fileFilter: (req, file, cb) => {
    cb(null, allowedTypes.includes(file.mimetype));
  },
});

function genId() {
  return Math.random().toString(36).substr(2, 9);
}

// Find admin user helper
function getAdminByIdAndPassword(id, password) {
  return users.find((u) => u.id === id && u.isAdmin && password === ADMINPASSWORD);
}

// Login route (admin or anonymous)
app.post('/login', (req, res) => {
  const { name, password, isAnonymous } = req.body;
  if (isAnonymous) {
    const user = {
      id: genId(),
      name: `Anonymous${genId()}`,
      isAdmin: false,
      isAnonymous: true,
    };
    users.push(user);
    saveData(usersFile, users);
    return res.json(user);
  }
  if (!name) return res.status(400).json({ error: 'Name required' });

  const isAdmin = name.toLowerCase() === 'admin' && password === ADMINPASSWORD;
  const user = {
    id: genId(),
    name,
    isAdmin,
    isAnonymous: false,
  };
  users.push(user);
  saveData(usersFile, users);
  res.json(user);
});

// Upload endpoint
app.post('/upload', upload.single('file'), (req, res) => {
  const { uploaderId, uploaderName, isAnonymous } = req.body;
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
  if (!uploaderId && !isAnonymous && !uploaderName)
    return res.status(400).json({ error: 'Uploader info required' });

  // Store file metadata associated with user
  // For demo, just respond success

  res.json({ success: true, fileId: req.file.filename, originalName: req.file.originalname });
});

// Admin approve file (mock)
app.post('/admin/approve', (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword))
    return res.status(403).json({ error: 'Admin only or wrong password' });
  res.json({ success: true });
});

app.post('/admin/reject', (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword))
    return res.status(403).json({ error: 'Admin only or wrong password' });
  res.json({ success: true });
});

// Download file route
app.get('/download/:fileId/:userId', (req, res) => {
  const { fileId, userId } = req.params;
  const user = users.find((u) => u.id === userId);
  if (!user) return res.status(403).json({ error: 'User not found' });

  const filePath = path.join(uploadsDir, fileId);
  if (!fs.existsSync(filePath)) return res.status(404).json({ error: 'File not found' });

  res.download(filePath);
});

// Upvote route (mock)
app.post('/upvote', (req, res) => {
  res.json({ success: true });
});

// List files route
app.get('/files/:userId', (req, res) => {
  const user = users.find((u) => u.id === req.params.userId);
  // Mock files response depending on admin or not
  if (user && user.isAdmin) {
    res.json([{ id: 'file1', originalName: 'AdminFile.pdf', isApproved: true }]);
  } else {
    res.json([{ id: 'file1', originalName: 'PublicFile.pdf', isApproved: true }]);
  }
});

// Comment submission
app.post('/comment', (req, res) => {
  const { text, authorName, authorId } = req.body;
  if (!text || !authorName) return res.status(400).json({ error: 'Comment or name required' });

  const comment = { id: genId(), text, authorName, authorId: authorId || null, createdAt: new Date() };
  comments.push(comment);
  saveData(commentsFile, comments);
  res.json({ success: true, comment });
});

app.get('/comments', (req, res) => {
  res.json(comments);
});

// Admin dashboard stats
app.get('/admin/stats/:adminId/:adminPassword', (req, res) => {
  const { adminId, adminPassword } = req.params;
  if (!getAdminByIdAndPassword(adminId, adminPassword))
    return res.status(403).json({ error: 'Admin only or wrong password' });

  res.json({
    totalFiles: 10,
    approved: 7,
    pending: 3,
    totalUpvotes: 15,
  });
});

app.listen(PORT, () => {
  console.log(`ShareLit backend running on port ${PORT}`);
});
