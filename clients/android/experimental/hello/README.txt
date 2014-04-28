Installing the self-signed goviewfinder.com certificate:
download BouncyCastleProvider: http://bouncycastle.org/
$ keytool -importcert -v -trustcacerts -file ~/viewfinder/secrets/goviewfinder.com/goviewfinder.com.crt -alias GoViewfinder -keystore "res/raw/myKeystore.bks" -provider org.bouncycastle.jce.provider.BouncyCastleProvider -providerpath "/tmp/bcprov-jdk16-145.jar" -storetype BKS -storepass local_pwd

Adding custom dns entry for goviewfinder.com to point to machine running the emulator:
https://sites.google.com/a/viewfinder.co/development/developer-setup/android-development
