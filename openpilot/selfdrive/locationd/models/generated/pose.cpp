#include "pose.h"

namespace {
#define DIM 18
#define EDIM 18
#define MEDIM 18
typedef void (*Hfun)(double *, double *, double *);
const static double MAHA_THRESH_4 = 7.814727903251177;
const static double MAHA_THRESH_10 = 7.814727903251177;
const static double MAHA_THRESH_13 = 7.814727903251177;
const static double MAHA_THRESH_14 = 7.814727903251177;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_5466562818920560471) {
   out_5466562818920560471[0] = delta_x[0] + nom_x[0];
   out_5466562818920560471[1] = delta_x[1] + nom_x[1];
   out_5466562818920560471[2] = delta_x[2] + nom_x[2];
   out_5466562818920560471[3] = delta_x[3] + nom_x[3];
   out_5466562818920560471[4] = delta_x[4] + nom_x[4];
   out_5466562818920560471[5] = delta_x[5] + nom_x[5];
   out_5466562818920560471[6] = delta_x[6] + nom_x[6];
   out_5466562818920560471[7] = delta_x[7] + nom_x[7];
   out_5466562818920560471[8] = delta_x[8] + nom_x[8];
   out_5466562818920560471[9] = delta_x[9] + nom_x[9];
   out_5466562818920560471[10] = delta_x[10] + nom_x[10];
   out_5466562818920560471[11] = delta_x[11] + nom_x[11];
   out_5466562818920560471[12] = delta_x[12] + nom_x[12];
   out_5466562818920560471[13] = delta_x[13] + nom_x[13];
   out_5466562818920560471[14] = delta_x[14] + nom_x[14];
   out_5466562818920560471[15] = delta_x[15] + nom_x[15];
   out_5466562818920560471[16] = delta_x[16] + nom_x[16];
   out_5466562818920560471[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_1362104546618899903) {
   out_1362104546618899903[0] = -nom_x[0] + true_x[0];
   out_1362104546618899903[1] = -nom_x[1] + true_x[1];
   out_1362104546618899903[2] = -nom_x[2] + true_x[2];
   out_1362104546618899903[3] = -nom_x[3] + true_x[3];
   out_1362104546618899903[4] = -nom_x[4] + true_x[4];
   out_1362104546618899903[5] = -nom_x[5] + true_x[5];
   out_1362104546618899903[6] = -nom_x[6] + true_x[6];
   out_1362104546618899903[7] = -nom_x[7] + true_x[7];
   out_1362104546618899903[8] = -nom_x[8] + true_x[8];
   out_1362104546618899903[9] = -nom_x[9] + true_x[9];
   out_1362104546618899903[10] = -nom_x[10] + true_x[10];
   out_1362104546618899903[11] = -nom_x[11] + true_x[11];
   out_1362104546618899903[12] = -nom_x[12] + true_x[12];
   out_1362104546618899903[13] = -nom_x[13] + true_x[13];
   out_1362104546618899903[14] = -nom_x[14] + true_x[14];
   out_1362104546618899903[15] = -nom_x[15] + true_x[15];
   out_1362104546618899903[16] = -nom_x[16] + true_x[16];
   out_1362104546618899903[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_1079315633669929618) {
   out_1079315633669929618[0] = 1.0;
   out_1079315633669929618[1] = 0.0;
   out_1079315633669929618[2] = 0.0;
   out_1079315633669929618[3] = 0.0;
   out_1079315633669929618[4] = 0.0;
   out_1079315633669929618[5] = 0.0;
   out_1079315633669929618[6] = 0.0;
   out_1079315633669929618[7] = 0.0;
   out_1079315633669929618[8] = 0.0;
   out_1079315633669929618[9] = 0.0;
   out_1079315633669929618[10] = 0.0;
   out_1079315633669929618[11] = 0.0;
   out_1079315633669929618[12] = 0.0;
   out_1079315633669929618[13] = 0.0;
   out_1079315633669929618[14] = 0.0;
   out_1079315633669929618[15] = 0.0;
   out_1079315633669929618[16] = 0.0;
   out_1079315633669929618[17] = 0.0;
   out_1079315633669929618[18] = 0.0;
   out_1079315633669929618[19] = 1.0;
   out_1079315633669929618[20] = 0.0;
   out_1079315633669929618[21] = 0.0;
   out_1079315633669929618[22] = 0.0;
   out_1079315633669929618[23] = 0.0;
   out_1079315633669929618[24] = 0.0;
   out_1079315633669929618[25] = 0.0;
   out_1079315633669929618[26] = 0.0;
   out_1079315633669929618[27] = 0.0;
   out_1079315633669929618[28] = 0.0;
   out_1079315633669929618[29] = 0.0;
   out_1079315633669929618[30] = 0.0;
   out_1079315633669929618[31] = 0.0;
   out_1079315633669929618[32] = 0.0;
   out_1079315633669929618[33] = 0.0;
   out_1079315633669929618[34] = 0.0;
   out_1079315633669929618[35] = 0.0;
   out_1079315633669929618[36] = 0.0;
   out_1079315633669929618[37] = 0.0;
   out_1079315633669929618[38] = 1.0;
   out_1079315633669929618[39] = 0.0;
   out_1079315633669929618[40] = 0.0;
   out_1079315633669929618[41] = 0.0;
   out_1079315633669929618[42] = 0.0;
   out_1079315633669929618[43] = 0.0;
   out_1079315633669929618[44] = 0.0;
   out_1079315633669929618[45] = 0.0;
   out_1079315633669929618[46] = 0.0;
   out_1079315633669929618[47] = 0.0;
   out_1079315633669929618[48] = 0.0;
   out_1079315633669929618[49] = 0.0;
   out_1079315633669929618[50] = 0.0;
   out_1079315633669929618[51] = 0.0;
   out_1079315633669929618[52] = 0.0;
   out_1079315633669929618[53] = 0.0;
   out_1079315633669929618[54] = 0.0;
   out_1079315633669929618[55] = 0.0;
   out_1079315633669929618[56] = 0.0;
   out_1079315633669929618[57] = 1.0;
   out_1079315633669929618[58] = 0.0;
   out_1079315633669929618[59] = 0.0;
   out_1079315633669929618[60] = 0.0;
   out_1079315633669929618[61] = 0.0;
   out_1079315633669929618[62] = 0.0;
   out_1079315633669929618[63] = 0.0;
   out_1079315633669929618[64] = 0.0;
   out_1079315633669929618[65] = 0.0;
   out_1079315633669929618[66] = 0.0;
   out_1079315633669929618[67] = 0.0;
   out_1079315633669929618[68] = 0.0;
   out_1079315633669929618[69] = 0.0;
   out_1079315633669929618[70] = 0.0;
   out_1079315633669929618[71] = 0.0;
   out_1079315633669929618[72] = 0.0;
   out_1079315633669929618[73] = 0.0;
   out_1079315633669929618[74] = 0.0;
   out_1079315633669929618[75] = 0.0;
   out_1079315633669929618[76] = 1.0;
   out_1079315633669929618[77] = 0.0;
   out_1079315633669929618[78] = 0.0;
   out_1079315633669929618[79] = 0.0;
   out_1079315633669929618[80] = 0.0;
   out_1079315633669929618[81] = 0.0;
   out_1079315633669929618[82] = 0.0;
   out_1079315633669929618[83] = 0.0;
   out_1079315633669929618[84] = 0.0;
   out_1079315633669929618[85] = 0.0;
   out_1079315633669929618[86] = 0.0;
   out_1079315633669929618[87] = 0.0;
   out_1079315633669929618[88] = 0.0;
   out_1079315633669929618[89] = 0.0;
   out_1079315633669929618[90] = 0.0;
   out_1079315633669929618[91] = 0.0;
   out_1079315633669929618[92] = 0.0;
   out_1079315633669929618[93] = 0.0;
   out_1079315633669929618[94] = 0.0;
   out_1079315633669929618[95] = 1.0;
   out_1079315633669929618[96] = 0.0;
   out_1079315633669929618[97] = 0.0;
   out_1079315633669929618[98] = 0.0;
   out_1079315633669929618[99] = 0.0;
   out_1079315633669929618[100] = 0.0;
   out_1079315633669929618[101] = 0.0;
   out_1079315633669929618[102] = 0.0;
   out_1079315633669929618[103] = 0.0;
   out_1079315633669929618[104] = 0.0;
   out_1079315633669929618[105] = 0.0;
   out_1079315633669929618[106] = 0.0;
   out_1079315633669929618[107] = 0.0;
   out_1079315633669929618[108] = 0.0;
   out_1079315633669929618[109] = 0.0;
   out_1079315633669929618[110] = 0.0;
   out_1079315633669929618[111] = 0.0;
   out_1079315633669929618[112] = 0.0;
   out_1079315633669929618[113] = 0.0;
   out_1079315633669929618[114] = 1.0;
   out_1079315633669929618[115] = 0.0;
   out_1079315633669929618[116] = 0.0;
   out_1079315633669929618[117] = 0.0;
   out_1079315633669929618[118] = 0.0;
   out_1079315633669929618[119] = 0.0;
   out_1079315633669929618[120] = 0.0;
   out_1079315633669929618[121] = 0.0;
   out_1079315633669929618[122] = 0.0;
   out_1079315633669929618[123] = 0.0;
   out_1079315633669929618[124] = 0.0;
   out_1079315633669929618[125] = 0.0;
   out_1079315633669929618[126] = 0.0;
   out_1079315633669929618[127] = 0.0;
   out_1079315633669929618[128] = 0.0;
   out_1079315633669929618[129] = 0.0;
   out_1079315633669929618[130] = 0.0;
   out_1079315633669929618[131] = 0.0;
   out_1079315633669929618[132] = 0.0;
   out_1079315633669929618[133] = 1.0;
   out_1079315633669929618[134] = 0.0;
   out_1079315633669929618[135] = 0.0;
   out_1079315633669929618[136] = 0.0;
   out_1079315633669929618[137] = 0.0;
   out_1079315633669929618[138] = 0.0;
   out_1079315633669929618[139] = 0.0;
   out_1079315633669929618[140] = 0.0;
   out_1079315633669929618[141] = 0.0;
   out_1079315633669929618[142] = 0.0;
   out_1079315633669929618[143] = 0.0;
   out_1079315633669929618[144] = 0.0;
   out_1079315633669929618[145] = 0.0;
   out_1079315633669929618[146] = 0.0;
   out_1079315633669929618[147] = 0.0;
   out_1079315633669929618[148] = 0.0;
   out_1079315633669929618[149] = 0.0;
   out_1079315633669929618[150] = 0.0;
   out_1079315633669929618[151] = 0.0;
   out_1079315633669929618[152] = 1.0;
   out_1079315633669929618[153] = 0.0;
   out_1079315633669929618[154] = 0.0;
   out_1079315633669929618[155] = 0.0;
   out_1079315633669929618[156] = 0.0;
   out_1079315633669929618[157] = 0.0;
   out_1079315633669929618[158] = 0.0;
   out_1079315633669929618[159] = 0.0;
   out_1079315633669929618[160] = 0.0;
   out_1079315633669929618[161] = 0.0;
   out_1079315633669929618[162] = 0.0;
   out_1079315633669929618[163] = 0.0;
   out_1079315633669929618[164] = 0.0;
   out_1079315633669929618[165] = 0.0;
   out_1079315633669929618[166] = 0.0;
   out_1079315633669929618[167] = 0.0;
   out_1079315633669929618[168] = 0.0;
   out_1079315633669929618[169] = 0.0;
   out_1079315633669929618[170] = 0.0;
   out_1079315633669929618[171] = 1.0;
   out_1079315633669929618[172] = 0.0;
   out_1079315633669929618[173] = 0.0;
   out_1079315633669929618[174] = 0.0;
   out_1079315633669929618[175] = 0.0;
   out_1079315633669929618[176] = 0.0;
   out_1079315633669929618[177] = 0.0;
   out_1079315633669929618[178] = 0.0;
   out_1079315633669929618[179] = 0.0;
   out_1079315633669929618[180] = 0.0;
   out_1079315633669929618[181] = 0.0;
   out_1079315633669929618[182] = 0.0;
   out_1079315633669929618[183] = 0.0;
   out_1079315633669929618[184] = 0.0;
   out_1079315633669929618[185] = 0.0;
   out_1079315633669929618[186] = 0.0;
   out_1079315633669929618[187] = 0.0;
   out_1079315633669929618[188] = 0.0;
   out_1079315633669929618[189] = 0.0;
   out_1079315633669929618[190] = 1.0;
   out_1079315633669929618[191] = 0.0;
   out_1079315633669929618[192] = 0.0;
   out_1079315633669929618[193] = 0.0;
   out_1079315633669929618[194] = 0.0;
   out_1079315633669929618[195] = 0.0;
   out_1079315633669929618[196] = 0.0;
   out_1079315633669929618[197] = 0.0;
   out_1079315633669929618[198] = 0.0;
   out_1079315633669929618[199] = 0.0;
   out_1079315633669929618[200] = 0.0;
   out_1079315633669929618[201] = 0.0;
   out_1079315633669929618[202] = 0.0;
   out_1079315633669929618[203] = 0.0;
   out_1079315633669929618[204] = 0.0;
   out_1079315633669929618[205] = 0.0;
   out_1079315633669929618[206] = 0.0;
   out_1079315633669929618[207] = 0.0;
   out_1079315633669929618[208] = 0.0;
   out_1079315633669929618[209] = 1.0;
   out_1079315633669929618[210] = 0.0;
   out_1079315633669929618[211] = 0.0;
   out_1079315633669929618[212] = 0.0;
   out_1079315633669929618[213] = 0.0;
   out_1079315633669929618[214] = 0.0;
   out_1079315633669929618[215] = 0.0;
   out_1079315633669929618[216] = 0.0;
   out_1079315633669929618[217] = 0.0;
   out_1079315633669929618[218] = 0.0;
   out_1079315633669929618[219] = 0.0;
   out_1079315633669929618[220] = 0.0;
   out_1079315633669929618[221] = 0.0;
   out_1079315633669929618[222] = 0.0;
   out_1079315633669929618[223] = 0.0;
   out_1079315633669929618[224] = 0.0;
   out_1079315633669929618[225] = 0.0;
   out_1079315633669929618[226] = 0.0;
   out_1079315633669929618[227] = 0.0;
   out_1079315633669929618[228] = 1.0;
   out_1079315633669929618[229] = 0.0;
   out_1079315633669929618[230] = 0.0;
   out_1079315633669929618[231] = 0.0;
   out_1079315633669929618[232] = 0.0;
   out_1079315633669929618[233] = 0.0;
   out_1079315633669929618[234] = 0.0;
   out_1079315633669929618[235] = 0.0;
   out_1079315633669929618[236] = 0.0;
   out_1079315633669929618[237] = 0.0;
   out_1079315633669929618[238] = 0.0;
   out_1079315633669929618[239] = 0.0;
   out_1079315633669929618[240] = 0.0;
   out_1079315633669929618[241] = 0.0;
   out_1079315633669929618[242] = 0.0;
   out_1079315633669929618[243] = 0.0;
   out_1079315633669929618[244] = 0.0;
   out_1079315633669929618[245] = 0.0;
   out_1079315633669929618[246] = 0.0;
   out_1079315633669929618[247] = 1.0;
   out_1079315633669929618[248] = 0.0;
   out_1079315633669929618[249] = 0.0;
   out_1079315633669929618[250] = 0.0;
   out_1079315633669929618[251] = 0.0;
   out_1079315633669929618[252] = 0.0;
   out_1079315633669929618[253] = 0.0;
   out_1079315633669929618[254] = 0.0;
   out_1079315633669929618[255] = 0.0;
   out_1079315633669929618[256] = 0.0;
   out_1079315633669929618[257] = 0.0;
   out_1079315633669929618[258] = 0.0;
   out_1079315633669929618[259] = 0.0;
   out_1079315633669929618[260] = 0.0;
   out_1079315633669929618[261] = 0.0;
   out_1079315633669929618[262] = 0.0;
   out_1079315633669929618[263] = 0.0;
   out_1079315633669929618[264] = 0.0;
   out_1079315633669929618[265] = 0.0;
   out_1079315633669929618[266] = 1.0;
   out_1079315633669929618[267] = 0.0;
   out_1079315633669929618[268] = 0.0;
   out_1079315633669929618[269] = 0.0;
   out_1079315633669929618[270] = 0.0;
   out_1079315633669929618[271] = 0.0;
   out_1079315633669929618[272] = 0.0;
   out_1079315633669929618[273] = 0.0;
   out_1079315633669929618[274] = 0.0;
   out_1079315633669929618[275] = 0.0;
   out_1079315633669929618[276] = 0.0;
   out_1079315633669929618[277] = 0.0;
   out_1079315633669929618[278] = 0.0;
   out_1079315633669929618[279] = 0.0;
   out_1079315633669929618[280] = 0.0;
   out_1079315633669929618[281] = 0.0;
   out_1079315633669929618[282] = 0.0;
   out_1079315633669929618[283] = 0.0;
   out_1079315633669929618[284] = 0.0;
   out_1079315633669929618[285] = 1.0;
   out_1079315633669929618[286] = 0.0;
   out_1079315633669929618[287] = 0.0;
   out_1079315633669929618[288] = 0.0;
   out_1079315633669929618[289] = 0.0;
   out_1079315633669929618[290] = 0.0;
   out_1079315633669929618[291] = 0.0;
   out_1079315633669929618[292] = 0.0;
   out_1079315633669929618[293] = 0.0;
   out_1079315633669929618[294] = 0.0;
   out_1079315633669929618[295] = 0.0;
   out_1079315633669929618[296] = 0.0;
   out_1079315633669929618[297] = 0.0;
   out_1079315633669929618[298] = 0.0;
   out_1079315633669929618[299] = 0.0;
   out_1079315633669929618[300] = 0.0;
   out_1079315633669929618[301] = 0.0;
   out_1079315633669929618[302] = 0.0;
   out_1079315633669929618[303] = 0.0;
   out_1079315633669929618[304] = 1.0;
   out_1079315633669929618[305] = 0.0;
   out_1079315633669929618[306] = 0.0;
   out_1079315633669929618[307] = 0.0;
   out_1079315633669929618[308] = 0.0;
   out_1079315633669929618[309] = 0.0;
   out_1079315633669929618[310] = 0.0;
   out_1079315633669929618[311] = 0.0;
   out_1079315633669929618[312] = 0.0;
   out_1079315633669929618[313] = 0.0;
   out_1079315633669929618[314] = 0.0;
   out_1079315633669929618[315] = 0.0;
   out_1079315633669929618[316] = 0.0;
   out_1079315633669929618[317] = 0.0;
   out_1079315633669929618[318] = 0.0;
   out_1079315633669929618[319] = 0.0;
   out_1079315633669929618[320] = 0.0;
   out_1079315633669929618[321] = 0.0;
   out_1079315633669929618[322] = 0.0;
   out_1079315633669929618[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_5100720361949642007) {
   out_5100720361949642007[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_5100720361949642007[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_5100720361949642007[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_5100720361949642007[3] = dt*state[12] + state[3];
   out_5100720361949642007[4] = dt*state[13] + state[4];
   out_5100720361949642007[5] = dt*state[14] + state[5];
   out_5100720361949642007[6] = state[6];
   out_5100720361949642007[7] = state[7];
   out_5100720361949642007[8] = state[8];
   out_5100720361949642007[9] = state[9];
   out_5100720361949642007[10] = state[10];
   out_5100720361949642007[11] = state[11];
   out_5100720361949642007[12] = state[12];
   out_5100720361949642007[13] = state[13];
   out_5100720361949642007[14] = state[14];
   out_5100720361949642007[15] = state[15];
   out_5100720361949642007[16] = state[16];
   out_5100720361949642007[17] = state[17];
}
void F_fun(double *state, double dt, double *out_3380236388623495731) {
   out_3380236388623495731[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3380236388623495731[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3380236388623495731[2] = 0;
   out_3380236388623495731[3] = 0;
   out_3380236388623495731[4] = 0;
   out_3380236388623495731[5] = 0;
   out_3380236388623495731[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3380236388623495731[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3380236388623495731[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3380236388623495731[9] = 0;
   out_3380236388623495731[10] = 0;
   out_3380236388623495731[11] = 0;
   out_3380236388623495731[12] = 0;
   out_3380236388623495731[13] = 0;
   out_3380236388623495731[14] = 0;
   out_3380236388623495731[15] = 0;
   out_3380236388623495731[16] = 0;
   out_3380236388623495731[17] = 0;
   out_3380236388623495731[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3380236388623495731[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3380236388623495731[20] = 0;
   out_3380236388623495731[21] = 0;
   out_3380236388623495731[22] = 0;
   out_3380236388623495731[23] = 0;
   out_3380236388623495731[24] = 0;
   out_3380236388623495731[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3380236388623495731[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3380236388623495731[27] = 0;
   out_3380236388623495731[28] = 0;
   out_3380236388623495731[29] = 0;
   out_3380236388623495731[30] = 0;
   out_3380236388623495731[31] = 0;
   out_3380236388623495731[32] = 0;
   out_3380236388623495731[33] = 0;
   out_3380236388623495731[34] = 0;
   out_3380236388623495731[35] = 0;
   out_3380236388623495731[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3380236388623495731[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3380236388623495731[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3380236388623495731[39] = 0;
   out_3380236388623495731[40] = 0;
   out_3380236388623495731[41] = 0;
   out_3380236388623495731[42] = 0;
   out_3380236388623495731[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3380236388623495731[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3380236388623495731[45] = 0;
   out_3380236388623495731[46] = 0;
   out_3380236388623495731[47] = 0;
   out_3380236388623495731[48] = 0;
   out_3380236388623495731[49] = 0;
   out_3380236388623495731[50] = 0;
   out_3380236388623495731[51] = 0;
   out_3380236388623495731[52] = 0;
   out_3380236388623495731[53] = 0;
   out_3380236388623495731[54] = 0;
   out_3380236388623495731[55] = 0;
   out_3380236388623495731[56] = 0;
   out_3380236388623495731[57] = 1;
   out_3380236388623495731[58] = 0;
   out_3380236388623495731[59] = 0;
   out_3380236388623495731[60] = 0;
   out_3380236388623495731[61] = 0;
   out_3380236388623495731[62] = 0;
   out_3380236388623495731[63] = 0;
   out_3380236388623495731[64] = 0;
   out_3380236388623495731[65] = 0;
   out_3380236388623495731[66] = dt;
   out_3380236388623495731[67] = 0;
   out_3380236388623495731[68] = 0;
   out_3380236388623495731[69] = 0;
   out_3380236388623495731[70] = 0;
   out_3380236388623495731[71] = 0;
   out_3380236388623495731[72] = 0;
   out_3380236388623495731[73] = 0;
   out_3380236388623495731[74] = 0;
   out_3380236388623495731[75] = 0;
   out_3380236388623495731[76] = 1;
   out_3380236388623495731[77] = 0;
   out_3380236388623495731[78] = 0;
   out_3380236388623495731[79] = 0;
   out_3380236388623495731[80] = 0;
   out_3380236388623495731[81] = 0;
   out_3380236388623495731[82] = 0;
   out_3380236388623495731[83] = 0;
   out_3380236388623495731[84] = 0;
   out_3380236388623495731[85] = dt;
   out_3380236388623495731[86] = 0;
   out_3380236388623495731[87] = 0;
   out_3380236388623495731[88] = 0;
   out_3380236388623495731[89] = 0;
   out_3380236388623495731[90] = 0;
   out_3380236388623495731[91] = 0;
   out_3380236388623495731[92] = 0;
   out_3380236388623495731[93] = 0;
   out_3380236388623495731[94] = 0;
   out_3380236388623495731[95] = 1;
   out_3380236388623495731[96] = 0;
   out_3380236388623495731[97] = 0;
   out_3380236388623495731[98] = 0;
   out_3380236388623495731[99] = 0;
   out_3380236388623495731[100] = 0;
   out_3380236388623495731[101] = 0;
   out_3380236388623495731[102] = 0;
   out_3380236388623495731[103] = 0;
   out_3380236388623495731[104] = dt;
   out_3380236388623495731[105] = 0;
   out_3380236388623495731[106] = 0;
   out_3380236388623495731[107] = 0;
   out_3380236388623495731[108] = 0;
   out_3380236388623495731[109] = 0;
   out_3380236388623495731[110] = 0;
   out_3380236388623495731[111] = 0;
   out_3380236388623495731[112] = 0;
   out_3380236388623495731[113] = 0;
   out_3380236388623495731[114] = 1;
   out_3380236388623495731[115] = 0;
   out_3380236388623495731[116] = 0;
   out_3380236388623495731[117] = 0;
   out_3380236388623495731[118] = 0;
   out_3380236388623495731[119] = 0;
   out_3380236388623495731[120] = 0;
   out_3380236388623495731[121] = 0;
   out_3380236388623495731[122] = 0;
   out_3380236388623495731[123] = 0;
   out_3380236388623495731[124] = 0;
   out_3380236388623495731[125] = 0;
   out_3380236388623495731[126] = 0;
   out_3380236388623495731[127] = 0;
   out_3380236388623495731[128] = 0;
   out_3380236388623495731[129] = 0;
   out_3380236388623495731[130] = 0;
   out_3380236388623495731[131] = 0;
   out_3380236388623495731[132] = 0;
   out_3380236388623495731[133] = 1;
   out_3380236388623495731[134] = 0;
   out_3380236388623495731[135] = 0;
   out_3380236388623495731[136] = 0;
   out_3380236388623495731[137] = 0;
   out_3380236388623495731[138] = 0;
   out_3380236388623495731[139] = 0;
   out_3380236388623495731[140] = 0;
   out_3380236388623495731[141] = 0;
   out_3380236388623495731[142] = 0;
   out_3380236388623495731[143] = 0;
   out_3380236388623495731[144] = 0;
   out_3380236388623495731[145] = 0;
   out_3380236388623495731[146] = 0;
   out_3380236388623495731[147] = 0;
   out_3380236388623495731[148] = 0;
   out_3380236388623495731[149] = 0;
   out_3380236388623495731[150] = 0;
   out_3380236388623495731[151] = 0;
   out_3380236388623495731[152] = 1;
   out_3380236388623495731[153] = 0;
   out_3380236388623495731[154] = 0;
   out_3380236388623495731[155] = 0;
   out_3380236388623495731[156] = 0;
   out_3380236388623495731[157] = 0;
   out_3380236388623495731[158] = 0;
   out_3380236388623495731[159] = 0;
   out_3380236388623495731[160] = 0;
   out_3380236388623495731[161] = 0;
   out_3380236388623495731[162] = 0;
   out_3380236388623495731[163] = 0;
   out_3380236388623495731[164] = 0;
   out_3380236388623495731[165] = 0;
   out_3380236388623495731[166] = 0;
   out_3380236388623495731[167] = 0;
   out_3380236388623495731[168] = 0;
   out_3380236388623495731[169] = 0;
   out_3380236388623495731[170] = 0;
   out_3380236388623495731[171] = 1;
   out_3380236388623495731[172] = 0;
   out_3380236388623495731[173] = 0;
   out_3380236388623495731[174] = 0;
   out_3380236388623495731[175] = 0;
   out_3380236388623495731[176] = 0;
   out_3380236388623495731[177] = 0;
   out_3380236388623495731[178] = 0;
   out_3380236388623495731[179] = 0;
   out_3380236388623495731[180] = 0;
   out_3380236388623495731[181] = 0;
   out_3380236388623495731[182] = 0;
   out_3380236388623495731[183] = 0;
   out_3380236388623495731[184] = 0;
   out_3380236388623495731[185] = 0;
   out_3380236388623495731[186] = 0;
   out_3380236388623495731[187] = 0;
   out_3380236388623495731[188] = 0;
   out_3380236388623495731[189] = 0;
   out_3380236388623495731[190] = 1;
   out_3380236388623495731[191] = 0;
   out_3380236388623495731[192] = 0;
   out_3380236388623495731[193] = 0;
   out_3380236388623495731[194] = 0;
   out_3380236388623495731[195] = 0;
   out_3380236388623495731[196] = 0;
   out_3380236388623495731[197] = 0;
   out_3380236388623495731[198] = 0;
   out_3380236388623495731[199] = 0;
   out_3380236388623495731[200] = 0;
   out_3380236388623495731[201] = 0;
   out_3380236388623495731[202] = 0;
   out_3380236388623495731[203] = 0;
   out_3380236388623495731[204] = 0;
   out_3380236388623495731[205] = 0;
   out_3380236388623495731[206] = 0;
   out_3380236388623495731[207] = 0;
   out_3380236388623495731[208] = 0;
   out_3380236388623495731[209] = 1;
   out_3380236388623495731[210] = 0;
   out_3380236388623495731[211] = 0;
   out_3380236388623495731[212] = 0;
   out_3380236388623495731[213] = 0;
   out_3380236388623495731[214] = 0;
   out_3380236388623495731[215] = 0;
   out_3380236388623495731[216] = 0;
   out_3380236388623495731[217] = 0;
   out_3380236388623495731[218] = 0;
   out_3380236388623495731[219] = 0;
   out_3380236388623495731[220] = 0;
   out_3380236388623495731[221] = 0;
   out_3380236388623495731[222] = 0;
   out_3380236388623495731[223] = 0;
   out_3380236388623495731[224] = 0;
   out_3380236388623495731[225] = 0;
   out_3380236388623495731[226] = 0;
   out_3380236388623495731[227] = 0;
   out_3380236388623495731[228] = 1;
   out_3380236388623495731[229] = 0;
   out_3380236388623495731[230] = 0;
   out_3380236388623495731[231] = 0;
   out_3380236388623495731[232] = 0;
   out_3380236388623495731[233] = 0;
   out_3380236388623495731[234] = 0;
   out_3380236388623495731[235] = 0;
   out_3380236388623495731[236] = 0;
   out_3380236388623495731[237] = 0;
   out_3380236388623495731[238] = 0;
   out_3380236388623495731[239] = 0;
   out_3380236388623495731[240] = 0;
   out_3380236388623495731[241] = 0;
   out_3380236388623495731[242] = 0;
   out_3380236388623495731[243] = 0;
   out_3380236388623495731[244] = 0;
   out_3380236388623495731[245] = 0;
   out_3380236388623495731[246] = 0;
   out_3380236388623495731[247] = 1;
   out_3380236388623495731[248] = 0;
   out_3380236388623495731[249] = 0;
   out_3380236388623495731[250] = 0;
   out_3380236388623495731[251] = 0;
   out_3380236388623495731[252] = 0;
   out_3380236388623495731[253] = 0;
   out_3380236388623495731[254] = 0;
   out_3380236388623495731[255] = 0;
   out_3380236388623495731[256] = 0;
   out_3380236388623495731[257] = 0;
   out_3380236388623495731[258] = 0;
   out_3380236388623495731[259] = 0;
   out_3380236388623495731[260] = 0;
   out_3380236388623495731[261] = 0;
   out_3380236388623495731[262] = 0;
   out_3380236388623495731[263] = 0;
   out_3380236388623495731[264] = 0;
   out_3380236388623495731[265] = 0;
   out_3380236388623495731[266] = 1;
   out_3380236388623495731[267] = 0;
   out_3380236388623495731[268] = 0;
   out_3380236388623495731[269] = 0;
   out_3380236388623495731[270] = 0;
   out_3380236388623495731[271] = 0;
   out_3380236388623495731[272] = 0;
   out_3380236388623495731[273] = 0;
   out_3380236388623495731[274] = 0;
   out_3380236388623495731[275] = 0;
   out_3380236388623495731[276] = 0;
   out_3380236388623495731[277] = 0;
   out_3380236388623495731[278] = 0;
   out_3380236388623495731[279] = 0;
   out_3380236388623495731[280] = 0;
   out_3380236388623495731[281] = 0;
   out_3380236388623495731[282] = 0;
   out_3380236388623495731[283] = 0;
   out_3380236388623495731[284] = 0;
   out_3380236388623495731[285] = 1;
   out_3380236388623495731[286] = 0;
   out_3380236388623495731[287] = 0;
   out_3380236388623495731[288] = 0;
   out_3380236388623495731[289] = 0;
   out_3380236388623495731[290] = 0;
   out_3380236388623495731[291] = 0;
   out_3380236388623495731[292] = 0;
   out_3380236388623495731[293] = 0;
   out_3380236388623495731[294] = 0;
   out_3380236388623495731[295] = 0;
   out_3380236388623495731[296] = 0;
   out_3380236388623495731[297] = 0;
   out_3380236388623495731[298] = 0;
   out_3380236388623495731[299] = 0;
   out_3380236388623495731[300] = 0;
   out_3380236388623495731[301] = 0;
   out_3380236388623495731[302] = 0;
   out_3380236388623495731[303] = 0;
   out_3380236388623495731[304] = 1;
   out_3380236388623495731[305] = 0;
   out_3380236388623495731[306] = 0;
   out_3380236388623495731[307] = 0;
   out_3380236388623495731[308] = 0;
   out_3380236388623495731[309] = 0;
   out_3380236388623495731[310] = 0;
   out_3380236388623495731[311] = 0;
   out_3380236388623495731[312] = 0;
   out_3380236388623495731[313] = 0;
   out_3380236388623495731[314] = 0;
   out_3380236388623495731[315] = 0;
   out_3380236388623495731[316] = 0;
   out_3380236388623495731[317] = 0;
   out_3380236388623495731[318] = 0;
   out_3380236388623495731[319] = 0;
   out_3380236388623495731[320] = 0;
   out_3380236388623495731[321] = 0;
   out_3380236388623495731[322] = 0;
   out_3380236388623495731[323] = 1;
}
void h_4(double *state, double *unused, double *out_6455932907869978741) {
   out_6455932907869978741[0] = state[6] + state[9];
   out_6455932907869978741[1] = state[7] + state[10];
   out_6455932907869978741[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_1833476635724642225) {
   out_1833476635724642225[0] = 0;
   out_1833476635724642225[1] = 0;
   out_1833476635724642225[2] = 0;
   out_1833476635724642225[3] = 0;
   out_1833476635724642225[4] = 0;
   out_1833476635724642225[5] = 0;
   out_1833476635724642225[6] = 1;
   out_1833476635724642225[7] = 0;
   out_1833476635724642225[8] = 0;
   out_1833476635724642225[9] = 1;
   out_1833476635724642225[10] = 0;
   out_1833476635724642225[11] = 0;
   out_1833476635724642225[12] = 0;
   out_1833476635724642225[13] = 0;
   out_1833476635724642225[14] = 0;
   out_1833476635724642225[15] = 0;
   out_1833476635724642225[16] = 0;
   out_1833476635724642225[17] = 0;
   out_1833476635724642225[18] = 0;
   out_1833476635724642225[19] = 0;
   out_1833476635724642225[20] = 0;
   out_1833476635724642225[21] = 0;
   out_1833476635724642225[22] = 0;
   out_1833476635724642225[23] = 0;
   out_1833476635724642225[24] = 0;
   out_1833476635724642225[25] = 1;
   out_1833476635724642225[26] = 0;
   out_1833476635724642225[27] = 0;
   out_1833476635724642225[28] = 1;
   out_1833476635724642225[29] = 0;
   out_1833476635724642225[30] = 0;
   out_1833476635724642225[31] = 0;
   out_1833476635724642225[32] = 0;
   out_1833476635724642225[33] = 0;
   out_1833476635724642225[34] = 0;
   out_1833476635724642225[35] = 0;
   out_1833476635724642225[36] = 0;
   out_1833476635724642225[37] = 0;
   out_1833476635724642225[38] = 0;
   out_1833476635724642225[39] = 0;
   out_1833476635724642225[40] = 0;
   out_1833476635724642225[41] = 0;
   out_1833476635724642225[42] = 0;
   out_1833476635724642225[43] = 0;
   out_1833476635724642225[44] = 1;
   out_1833476635724642225[45] = 0;
   out_1833476635724642225[46] = 0;
   out_1833476635724642225[47] = 1;
   out_1833476635724642225[48] = 0;
   out_1833476635724642225[49] = 0;
   out_1833476635724642225[50] = 0;
   out_1833476635724642225[51] = 0;
   out_1833476635724642225[52] = 0;
   out_1833476635724642225[53] = 0;
}
void h_10(double *state, double *unused, double *out_7550405242873940214) {
   out_7550405242873940214[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_7550405242873940214[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_7550405242873940214[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_4785130908546047591) {
   out_4785130908546047591[0] = 0;
   out_4785130908546047591[1] = 9.8100000000000005*cos(state[1]);
   out_4785130908546047591[2] = 0;
   out_4785130908546047591[3] = 0;
   out_4785130908546047591[4] = -state[8];
   out_4785130908546047591[5] = state[7];
   out_4785130908546047591[6] = 0;
   out_4785130908546047591[7] = state[5];
   out_4785130908546047591[8] = -state[4];
   out_4785130908546047591[9] = 0;
   out_4785130908546047591[10] = 0;
   out_4785130908546047591[11] = 0;
   out_4785130908546047591[12] = 1;
   out_4785130908546047591[13] = 0;
   out_4785130908546047591[14] = 0;
   out_4785130908546047591[15] = 1;
   out_4785130908546047591[16] = 0;
   out_4785130908546047591[17] = 0;
   out_4785130908546047591[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_4785130908546047591[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_4785130908546047591[20] = 0;
   out_4785130908546047591[21] = state[8];
   out_4785130908546047591[22] = 0;
   out_4785130908546047591[23] = -state[6];
   out_4785130908546047591[24] = -state[5];
   out_4785130908546047591[25] = 0;
   out_4785130908546047591[26] = state[3];
   out_4785130908546047591[27] = 0;
   out_4785130908546047591[28] = 0;
   out_4785130908546047591[29] = 0;
   out_4785130908546047591[30] = 0;
   out_4785130908546047591[31] = 1;
   out_4785130908546047591[32] = 0;
   out_4785130908546047591[33] = 0;
   out_4785130908546047591[34] = 1;
   out_4785130908546047591[35] = 0;
   out_4785130908546047591[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_4785130908546047591[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_4785130908546047591[38] = 0;
   out_4785130908546047591[39] = -state[7];
   out_4785130908546047591[40] = state[6];
   out_4785130908546047591[41] = 0;
   out_4785130908546047591[42] = state[4];
   out_4785130908546047591[43] = -state[3];
   out_4785130908546047591[44] = 0;
   out_4785130908546047591[45] = 0;
   out_4785130908546047591[46] = 0;
   out_4785130908546047591[47] = 0;
   out_4785130908546047591[48] = 0;
   out_4785130908546047591[49] = 0;
   out_4785130908546047591[50] = 1;
   out_4785130908546047591[51] = 0;
   out_4785130908546047591[52] = 0;
   out_4785130908546047591[53] = 1;
}
void h_13(double *state, double *unused, double *out_9187434641215416987) {
   out_9187434641215416987[0] = state[3];
   out_9187434641215416987[1] = state[4];
   out_9187434641215416987[2] = state[5];
}
void H_13(double *state, double *unused, double *out_9002636229668208462) {
   out_9002636229668208462[0] = 0;
   out_9002636229668208462[1] = 0;
   out_9002636229668208462[2] = 0;
   out_9002636229668208462[3] = 1;
   out_9002636229668208462[4] = 0;
   out_9002636229668208462[5] = 0;
   out_9002636229668208462[6] = 0;
   out_9002636229668208462[7] = 0;
   out_9002636229668208462[8] = 0;
   out_9002636229668208462[9] = 0;
   out_9002636229668208462[10] = 0;
   out_9002636229668208462[11] = 0;
   out_9002636229668208462[12] = 0;
   out_9002636229668208462[13] = 0;
   out_9002636229668208462[14] = 0;
   out_9002636229668208462[15] = 0;
   out_9002636229668208462[16] = 0;
   out_9002636229668208462[17] = 0;
   out_9002636229668208462[18] = 0;
   out_9002636229668208462[19] = 0;
   out_9002636229668208462[20] = 0;
   out_9002636229668208462[21] = 0;
   out_9002636229668208462[22] = 1;
   out_9002636229668208462[23] = 0;
   out_9002636229668208462[24] = 0;
   out_9002636229668208462[25] = 0;
   out_9002636229668208462[26] = 0;
   out_9002636229668208462[27] = 0;
   out_9002636229668208462[28] = 0;
   out_9002636229668208462[29] = 0;
   out_9002636229668208462[30] = 0;
   out_9002636229668208462[31] = 0;
   out_9002636229668208462[32] = 0;
   out_9002636229668208462[33] = 0;
   out_9002636229668208462[34] = 0;
   out_9002636229668208462[35] = 0;
   out_9002636229668208462[36] = 0;
   out_9002636229668208462[37] = 0;
   out_9002636229668208462[38] = 0;
   out_9002636229668208462[39] = 0;
   out_9002636229668208462[40] = 0;
   out_9002636229668208462[41] = 1;
   out_9002636229668208462[42] = 0;
   out_9002636229668208462[43] = 0;
   out_9002636229668208462[44] = 0;
   out_9002636229668208462[45] = 0;
   out_9002636229668208462[46] = 0;
   out_9002636229668208462[47] = 0;
   out_9002636229668208462[48] = 0;
   out_9002636229668208462[49] = 0;
   out_9002636229668208462[50] = 0;
   out_9002636229668208462[51] = 0;
   out_9002636229668208462[52] = 0;
   out_9002636229668208462[53] = 0;
}
void h_14(double *state, double *unused, double *out_8472317454123513856) {
   out_8472317454123513856[0] = state[6];
   out_8472317454123513856[1] = state[7];
   out_8472317454123513856[2] = state[8];
}
void H_14(double *state, double *unused, double *out_5796717492064126754) {
   out_5796717492064126754[0] = 0;
   out_5796717492064126754[1] = 0;
   out_5796717492064126754[2] = 0;
   out_5796717492064126754[3] = 0;
   out_5796717492064126754[4] = 0;
   out_5796717492064126754[5] = 0;
   out_5796717492064126754[6] = 1;
   out_5796717492064126754[7] = 0;
   out_5796717492064126754[8] = 0;
   out_5796717492064126754[9] = 0;
   out_5796717492064126754[10] = 0;
   out_5796717492064126754[11] = 0;
   out_5796717492064126754[12] = 0;
   out_5796717492064126754[13] = 0;
   out_5796717492064126754[14] = 0;
   out_5796717492064126754[15] = 0;
   out_5796717492064126754[16] = 0;
   out_5796717492064126754[17] = 0;
   out_5796717492064126754[18] = 0;
   out_5796717492064126754[19] = 0;
   out_5796717492064126754[20] = 0;
   out_5796717492064126754[21] = 0;
   out_5796717492064126754[22] = 0;
   out_5796717492064126754[23] = 0;
   out_5796717492064126754[24] = 0;
   out_5796717492064126754[25] = 1;
   out_5796717492064126754[26] = 0;
   out_5796717492064126754[27] = 0;
   out_5796717492064126754[28] = 0;
   out_5796717492064126754[29] = 0;
   out_5796717492064126754[30] = 0;
   out_5796717492064126754[31] = 0;
   out_5796717492064126754[32] = 0;
   out_5796717492064126754[33] = 0;
   out_5796717492064126754[34] = 0;
   out_5796717492064126754[35] = 0;
   out_5796717492064126754[36] = 0;
   out_5796717492064126754[37] = 0;
   out_5796717492064126754[38] = 0;
   out_5796717492064126754[39] = 0;
   out_5796717492064126754[40] = 0;
   out_5796717492064126754[41] = 0;
   out_5796717492064126754[42] = 0;
   out_5796717492064126754[43] = 0;
   out_5796717492064126754[44] = 1;
   out_5796717492064126754[45] = 0;
   out_5796717492064126754[46] = 0;
   out_5796717492064126754[47] = 0;
   out_5796717492064126754[48] = 0;
   out_5796717492064126754[49] = 0;
   out_5796717492064126754[50] = 0;
   out_5796717492064126754[51] = 0;
   out_5796717492064126754[52] = 0;
   out_5796717492064126754[53] = 0;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_4, H_4, NULL, in_z, in_R, in_ea, MAHA_THRESH_4);
}
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_10, H_10, NULL, in_z, in_R, in_ea, MAHA_THRESH_10);
}
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_13, H_13, NULL, in_z, in_R, in_ea, MAHA_THRESH_13);
}
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_14, H_14, NULL, in_z, in_R, in_ea, MAHA_THRESH_14);
}
void pose_err_fun(double *nom_x, double *delta_x, double *out_5466562818920560471) {
  err_fun(nom_x, delta_x, out_5466562818920560471);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_1362104546618899903) {
  inv_err_fun(nom_x, true_x, out_1362104546618899903);
}
void pose_H_mod_fun(double *state, double *out_1079315633669929618) {
  H_mod_fun(state, out_1079315633669929618);
}
void pose_f_fun(double *state, double dt, double *out_5100720361949642007) {
  f_fun(state,  dt, out_5100720361949642007);
}
void pose_F_fun(double *state, double dt, double *out_3380236388623495731) {
  F_fun(state,  dt, out_3380236388623495731);
}
void pose_h_4(double *state, double *unused, double *out_6455932907869978741) {
  h_4(state, unused, out_6455932907869978741);
}
void pose_H_4(double *state, double *unused, double *out_1833476635724642225) {
  H_4(state, unused, out_1833476635724642225);
}
void pose_h_10(double *state, double *unused, double *out_7550405242873940214) {
  h_10(state, unused, out_7550405242873940214);
}
void pose_H_10(double *state, double *unused, double *out_4785130908546047591) {
  H_10(state, unused, out_4785130908546047591);
}
void pose_h_13(double *state, double *unused, double *out_9187434641215416987) {
  h_13(state, unused, out_9187434641215416987);
}
void pose_H_13(double *state, double *unused, double *out_9002636229668208462) {
  H_13(state, unused, out_9002636229668208462);
}
void pose_h_14(double *state, double *unused, double *out_8472317454123513856) {
  h_14(state, unused, out_8472317454123513856);
}
void pose_H_14(double *state, double *unused, double *out_5796717492064126754) {
  H_14(state, unused, out_5796717492064126754);
}
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
}

const EKF pose = {
  .name = "pose",
  .kinds = { 4, 10, 13, 14 },
  .feature_kinds = {  },
  .f_fun = pose_f_fun,
  .F_fun = pose_F_fun,
  .err_fun = pose_err_fun,
  .inv_err_fun = pose_inv_err_fun,
  .H_mod_fun = pose_H_mod_fun,
  .predict = pose_predict,
  .hs = {
    { 4, pose_h_4 },
    { 10, pose_h_10 },
    { 13, pose_h_13 },
    { 14, pose_h_14 },
  },
  .Hs = {
    { 4, pose_H_4 },
    { 10, pose_H_10 },
    { 13, pose_H_13 },
    { 14, pose_H_14 },
  },
  .updates = {
    { 4, pose_update_4 },
    { 10, pose_update_10 },
    { 13, pose_update_13 },
    { 14, pose_update_14 },
  },
  .Hes = {
  },
  .sets = {
  },
  .extra_routines = {
  },
};

ekf_lib_init(pose)
