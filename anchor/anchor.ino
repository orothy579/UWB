#include <SPI.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "dw3000.h"

// WiFi credentials
const char* ssid = "AIoT_2F";
const char* password = "monetghgh";

// Server endpoint
const char* serverName = "http://yourserver.com/api/timestamps";

const uint8_t PIN_RST = 27;  // reset pin
const uint8_t PIN_IRQ = 34;  // irq pin
const uint8_t PIN_SS = 4;    // spi select pin

#define RNG_DELAY_MS 1000
#define TX_ANT_DLY 16385
#define RX_ANT_DLY 16385
#define ALL_MSG_COMMON_LEN 10
#define ALL_MSG_SN_IDX 2
#define RESP_MSG_POLL_RX_TS_IDX 10
#define RESP_MSG_RESP_TX_TS_IDX 14
#define RESP_MSG_TS_LEN 4
#define POLL_TX_TO_RESP_RX_DLY_UUS 240
#define RESP_RX_TIMEOUT_UUS 400

static dwt_config_t config = {
  9,                /* Channel number. */
  DWT_PLEN_128,     /* Preamble length. Used in TX only. */
  DWT_PAC8,         /* Preamble acquisition chunk size. Used in RX only. */
  9,                /* TX preamble code. Used in TX only. */
  9,                /* RX preamble code. Used in RX only. */
  1,                /* Non-standard 8 symbol SFD */
  DWT_BR_6M8,       /* Data rate. */
  DWT_PHRMODE_STD,  /* PHY header mode. */
  DWT_PHRRATE_STD,  /* PHY header rate. */
  (129 + 8 - 8),    /* SFD timeout (preamble length + 1 + SFD length - PAC size). Used in RX only. */
  DWT_STS_MODE_OFF, /* STS disabled */
  DWT_STS_LEN_64,   /* STS length */
  DWT_PDOA_M0       /* PDOA mode off */
};

#define FRAME_LEN_MAX 127
#define FCS_LEN 2

// For Anchor 1
static uint8_t tx_frame[] = { 0xC5, 0, 'A', 'N', 'C', 'H', 'O', 'R', '_', 'I', 'D', 0x01, 0x01 };
static uint8_t rx_sync_msg[] = {0x41, 0x88, 0, 0xCA, 0xDE, 'W', 'A', 'V', 'E', 0xE0, 0, 0};

/* Buffer to store received frame. See NOTE 1 below. */
static uint8_t rx_buffer[FRAME_LEN_MAX];
/* Hold copy of status register state here for reference so that it can be examined at a debug breakpoint. */
uint32_t status_reg;
/* Hold copy of frame length of frame received (if good) so that it can be examined at a debug breakpoint. */
uint16_t frame_len;

void setup() {
  UART_init();

  /* Configure SPI rate, DW3000 supports up to 38 MHz */
  /* Reset DW IC */
  spiBegin(PIN_IRQ, PIN_RST);
  spiSelect(PIN_SS);

  delay(200);  // Time needed for DW3000 to start up (transition from INIT_RC to IDLE_RC, or could wait for SPIRDY event)

  while (!dwt_checkidlerc())  // Need to make sure DW IC is in IDLE_RC before proceeding
  {
    UART_puts("IDLE FAILED\r\n");
    while (1)
      ;
  }

  dwt_softreset();
  delay(200);

  if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR) {
    UART_puts("INIT FAILED\r\n");
    while (1)
      ;
  }

  // Enabling LEDs here for debug so that for each TX the D1 LED will flash on DW3000 red eval-shield boards.
  dwt_setleds(DWT_LEDS_ENABLE | DWT_LEDS_INIT_BLINK);

  // Configure DW IC. See NOTE 5 below.
  if (dwt_configure(&config))  // if the dwt_configure returns DWT_ERROR either the PLL or RX calibration has failed the host should reset the device
  {
    UART_puts("CONFIG FAILED\r\n");
    while (1)
      ;
  }

  // Connect to Wi-Fi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("WiFi connected");
}


void loop() {
  // Clear local RX buffer to avoid having leftovers from previous receptions
  memset(rx_buffer, 0, sizeof(rx_buffer));

  // Activate reception immediately
  dwt_rxenable(DWT_START_RX_IMMEDIATE);

  // Poll until a frame is properly received or an error/timeout occurs
  while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) & (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_ERR))) {
  };

  if (status_reg & SYS_STATUS_RXFCG_BIT_MASK) {
    // A frame has been received, copy it to our local buffer
    frame_len = dwt_read32bitreg(RX_FINFO_ID) & RX_FINFO_RXFLEN_BIT_MASK;
    if (frame_len <= FRAME_LEN_MAX) {
      dwt_readrxdata(rx_buffer, frame_len, 0);  // No need to read the FCS/CRC
      // if(memcmp(rx_buffer, rx_sync_msg, sizeof(rx_buffer)) == 0){
      //   Serial.println("SYNC message received");
      // } else {
      //   Serial.println("Non-SYNC message received");
      // }
      
      dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);

      Serial.println("Frame Received");

      // Read the timestamp when the frame was received
      uint64_t rx_time = dwt_readrxtimestamplo32();
      Serial.print("Received timestamp: ");
      Serial.println(rx_time);

      // Send timestamp to server
      sendTimestampsToServer("anchor", rx_time);

      Serial.println("Timestamp Sent");
    }


  } else {
    // Clear RX error events in the DW IC status register
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_ERR);
  }
}

void sendTimestampsToServer(const char* role, uint64_t timestamp) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;

    http.begin(serverName);

    http.addHeader("Content-Type", "application/json");

    String payload = "{ \"role\": \"" + String(role) + "\", \"timestamp\": " + String(timestamp) + " }";

    int httpResponseCode = http.POST(payload);

    if (httpResponseCode > 0) {
      String response = http.getString();
      // Serial.println(httpResponseCode);
      // Serial.println(response);
    } else {
      Serial.print("Error on sending POST: ");
      Serial.println(httpResponseCode);
    }

    http.end();
  } else {
    Serial.println("Error in WiFi connection");
  }
}
