/* libsodium-compatible sealed box (crypto_box_seal) on tweetnacl + blake2b.
   nonce = blake2b(ephemeral_pk || recipient_pk, 24 bytes); output = ephemeral_pk || box(msg). */
(function(g){
g.sealBox=function(msg,pk){
  var ek=g.nacl.box.keyPair(), n=new Uint8Array(64); n.set(ek.publicKey,0); n.set(pk,32);
  var nonce=g.blake2b(n,null,24), c=g.nacl.box(msg,nonce,pk,ek.secretKey), out=new Uint8Array(32+c.length);
  out.set(ek.publicKey,0); out.set(c,32); return out;
};
})(typeof window!=='undefined'?window:globalThis);
