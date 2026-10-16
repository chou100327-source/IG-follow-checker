// Google 登入 + Firestore 同步。未填 firebase-config.js 時整段停用，也不會載入 Firebase。
const cfg = window.FIREBASE_CONFIG;
if (cfg && cfg.apiKey) {
  const V = "https://www.gstatic.com/firebasejs/10.12.2/";
  const [{ initializeApp }, A, F] = await Promise.all([
    import(V + "firebase-app.js"),
    import(V + "firebase-auth.js"),
    import(V + "firebase-firestore.js")
  ]);
  const app = initializeApp(cfg);
  const auth = A.getAuth(app);
  const db = F.getFirestore(app);
  const snaps = uid => F.collection(db, "users", uid, "snapshots");

  window.cloud = {
    onAuth: cb => A.onAuthStateChanged(auth, cb),
    signIn: () => A.signInWithPopup(auth, new A.GoogleAuthProvider()),
    signOut: () => A.signOut(auth),
    // 最近 10 筆快照，新到舊
    async list() {
      const q = F.query(snaps(auth.currentUser.uid), F.orderBy("date", "desc"), F.limit(10));
      return (await F.getDocs(q)).docs.map(d => d.data());
    },
    // 同一天只保留一筆（文件 ID = 日期）
    save: s => F.setDoc(F.doc(snaps(auth.currentUser.uid), s.date), { date: s.date, followers: s.followers }),
    async wipe() {
      const all = await F.getDocs(snaps(auth.currentUser.uid));
      await Promise.all(all.docs.map(d => F.deleteDoc(d.ref)));
    }
  };
}
window.dispatchEvent(new Event("cloud-ready"));
